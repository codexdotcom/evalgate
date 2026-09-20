from __future__ import annotations
import asyncio, json, os, signal, time, logging

import asyncpg

from .scorers import ExactMatch, ToolCallSequence, NoLoops, StepBudget
from .judge import LLMJudge
from .execute import run_agent

log = logging.getLogger("worker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

SCORERS = [ExactMatch(), ToolCallSequence(), NoLoops(), StepBudget(), LLMJudge()]
CONFIDENCE_FLOOR = float(os.getenv("CONFIDENCE_FLOOR", "0.67"))
BATCH = int(os.getenv("BATCH", "16"))
CONCURRENCY = int(os.getenv("CONCURRENCY", "8"))
STALE_AFTER = os.getenv("STALE_AFTER", "10 minutes")
MAX_ATTEMPTS = int(os.getenv("MAX_ATTEMPTS", "3"))

# SKIP LOCKED is what lets N workers pull disjoint batches with no
# coordinator: each worker's SELECT steps over rows another worker has
# already locked instead of blocking on them.
CLAIM = """
UPDATE "Trajectory" SET status = 'RUNNING', attempt = attempt + 1
WHERE id IN (
  SELECT id FROM "Trajectory"
  WHERE status = 'QUEUED' AND attempt < $2
  ORDER BY id
  FOR UPDATE SKIP LOCKED
  LIMIT $1
)
RETURNING id, "runId", "taskCaseId"
"""

# A worker that dies mid-batch leaves rows stuck in RUNNING forever.
# The reaper is the crash-recovery half of the claim protocol.
REAP = f"""
UPDATE "Trajectory" SET status = 'QUEUED'
WHERE status = 'RUNNING'
  AND attempt < $1
  AND "updatedAt" < now() - interval '{STALE_AFTER}'
RETURNING id
"""


class Shutdown:
    """Flipped by SIGTERM. Stops new claims; in-flight work finishes."""
    def __init__(self) -> None:
        self.requested = False
        self.since: float | None = None

    def request(self, signame: str) -> None:
        if not self.requested:
            log.info("received %s, draining", signame)
            self.requested = True
            self.since = time.perf_counter()


async def load_case(con, task_case_id: str) -> dict:
    row = await con.fetchrow(
        'SELECT prompt, expected, rubric FROM "TaskCase" WHERE id = $1', task_case_id
    )
    return {
        "prompt": row["prompt"],
        "expected": json.loads(row["expected"]) if row["expected"] else None,
        "rubric": row["rubric"],
    }


async def persist(con, traj_id: str, run_id: str, traj: dict, results: list) -> None:
    verdicts = {r.scorer_key: r.passed for r in results}
    disagree = len(set(verdicts.values())) > 1
    low_conf = any(r.confidence < CONFIDENCE_FLOOR for r in results)

    async with con.transaction():
        await con.execute(
            'UPDATE "Trajectory" SET status=$2, steps=$3::jsonb, "finalOutput"=$4, '
            '"terminalState"=$5, "latencyMs"=$6, "inputTokens"=$7, "outputTokens"=$8, '
            '"costUsd"=$9, error=NULL WHERE id=$1',
            traj_id, "SCORED", json.dumps(traj["steps"]), traj["final_output"],
            traj["terminal_state"],
            sum(s.get("latency_ms", 0) for s in traj["steps"]),
            sum(s.get("input_tokens", 0) for s in traj["steps"]),
            sum(s.get("output_tokens", 0) for s in traj["steps"]),
            sum(r.cost_usd for r in results),
        )
        await con.executemany(
            'INSERT INTO "Score" (id,"trajectoryId","scorerKey","scorerKind",value,passed,'
            'confidence,rationale,"costUsd") '
            'VALUES (gen_random_uuid()::text,$1,$2,$3,$4,$5,$6,$7,$8) '
            'ON CONFLICT ("trajectoryId","scorerKey") DO UPDATE SET '
            'value=EXCLUDED.value, passed=EXCLUDED.passed, confidence=EXCLUDED.confidence, '
            'rationale=EXCLUDED.rationale, "costUsd"=EXCLUDED."costUsd"',
            [(traj_id, r.scorer_key, r.scorer_kind, r.value, r.passed,
              r.confidence, r.rationale, r.cost_usd) for r in results],
        )
        if disagree or low_conf:
            await con.execute(
                'INSERT INTO "Review" (id,"trajectoryId",reason) '
                'VALUES (gen_random_uuid()::text,$1,$2::"ReviewReason") '
                'ON CONFLICT ("trajectoryId") DO NOTHING',
                traj_id,
                "SCORER_DISAGREEMENT" if disagree else "LOW_CONFIDENCE",
            )
        await con.execute(
            'UPDATE "Run" SET "doneCases" = "doneCases" + 1 WHERE id = $1', run_id
        )
        await con.execute(
            'UPDATE "Run" SET status=\'COMPLETED\', "finishedAt"=now() '
            'WHERE id=$1 AND "doneCases" >= "totalCases" AND status=\'RUNNING\'',
            run_id,
        )


async def handle(pool, row) -> None:
    traj_id, run_id, case_id = row["id"], row["runId"], row["taskCaseId"]
    try:
        async with pool.acquire() as con:
            case = await load_case(con, case_id)
            model = await con.fetchval('SELECT model FROM "Run" WHERE id=$1', run_id)

        traj = await run_agent(case, model=model)
        results = await asyncio.gather(*(s.score(traj, case) for s in SCORERS))

        async with pool.acquire() as con:
            await persist(con, traj_id, run_id, traj, results)
    except Exception as exc:  # noqa: BLE001
        log.exception("trajectory %s failed", traj_id)
        async with pool.acquire() as con:
            # Under max attempts it goes back to QUEUED for another pass.
            await con.execute(
                'UPDATE "Trajectory" SET status = CASE WHEN attempt >= $3 '
                "THEN 'FAILED' ELSE 'QUEUED' END, error=$2 WHERE id=$1",
                traj_id, str(exc)[:500], MAX_ATTEMPTS,
            )


async def reaper(pool, shutdown: Shutdown) -> None:
    while not shutdown.requested:
        try:
            async with pool.acquire() as con:
                revived = await con.fetch(REAP, MAX_ATTEMPTS)
            if revived:
                log.warning("reaped %d stale RUNNING rows", len(revived))
        except Exception:  # noqa: BLE001
            log.exception("reaper pass failed")
        for _ in range(60):
            if shutdown.requested:
                return
            await asyncio.sleep(1)


async def main() -> None:
    pool = await asyncpg.create_pool(
        os.environ["DATABASE_URL"], min_size=2, max_size=CONCURRENCY + 4
    )
    shutdown = Shutdown()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, shutdown.request, sig.name)

    reap_task = asyncio.create_task(reaper(pool, shutdown))
    sem = asyncio.Semaphore(CONCURRENCY)
    inflight: set[asyncio.Task] = set()
    log.info("worker up, concurrency=%d batch=%d", CONCURRENCY, BATCH)

    async def guarded(row) -> None:
        async with sem:
            await handle(pool, row)

    try:
        while not shutdown.requested:
            headroom = CONCURRENCY - len(inflight)
            if headroom <= 0:
                await asyncio.sleep(0.05)
                continue

            async with pool.acquire() as con:
                rows = await con.fetch(CLAIM, min(BATCH, headroom), MAX_ATTEMPTS)

            if not rows:
                await asyncio.sleep(1.0)
                continue

            for row in rows:
                task = asyncio.create_task(guarded(row))
                inflight.add(task)
                task.add_done_callback(inflight.discard)
    finally:
        if inflight:
            log.info("draining %d in-flight trajectories", len(inflight))
            await asyncio.gather(*inflight, return_exceptions=True)
        reap_task.cancel()
        await pool.close()
        took = time.perf_counter() - (shutdown.since or time.perf_counter())
        log.info("drained cleanly in %.1fs", took)


if __name__ == "__main__":
    asyncio.run(main())