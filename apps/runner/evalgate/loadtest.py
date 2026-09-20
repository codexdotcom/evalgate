import asyncio, os, random, statistics, time, json
import asyncpg

MOCK_TOOLS = ["search", "read_file", "write_file", "run_tests", "finish"]

def synth_trajectory(seed: int) -> dict:
    rnd = random.Random(seed)
    n = rnd.randint(3, 12)
    steps = []
    for i in range(n):
        steps.append({
            "index": i,
            "role": "assistant" if i % 2 == 0 else "tool",
            "content": f"step {i} reasoning" if i % 2 == 0 else "",
            "tool_calls": (
                [{"id": f"t{i}", "name": rnd.choice(MOCK_TOOLS), "args": {"q": i}}]
                if i % 2 == 0 else []
            ),
            "tool_result": None if i % 2 == 0 else f"result {i}",
            "latency_ms": rnd.randint(200, 1400),
            "input_tokens": rnd.randint(300, 2000),
            "output_tokens": rnd.randint(50, 400),
        })
    return {
        "steps": steps,
        "final_output": "done" if rnd.random() > 0.25 else "could not complete",
        "terminal_state": "completed" if rnd.random() > 0.15 else "max_steps",
    }

async def seed_suite(pool, n_cases: int, slug="loadtest"):
    async with pool.acquire() as con:
        suite_id = await con.fetchval(
            'INSERT INTO "Suite" (id, slug, name) VALUES (gen_random_uuid()::text,$1,$2) '
            'ON CONFLICT (slug) DO UPDATE SET name=EXCLUDED.name RETURNING id',
            slug, "Load test suite")
        await con.executemany(
            'INSERT INTO "TaskCase" (id,"suiteId","externalId",prompt,expected,rubric,tags) '
            'VALUES (gen_random_uuid()::text,$1,$2,$3,$4,$5,$6) '
            'ON CONFLICT ("suiteId","externalId") DO NOTHING',
            [(suite_id, f"lt-{i}", f"Synthetic task {i}",
              json.dumps({"tool_sequence": ["search", "finish"]}),
              "The agent completed the task.", ["loadtest"])
             for i in range(n_cases)])
    return suite_id

async def main():
    n = int(os.getenv("N_CASES", "10000"))
    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=2, max_size=8)
    t0 = time.perf_counter()
    suite_id = await seed_suite(pool, n)
    print(f"seeded {n} cases in {time.perf_counter()-t0:.1f}s")

    async with pool.acquire() as con:
        run_id = await con.fetchval(
            'INSERT INTO "Run" (id,"suiteId",model,config,"totalCases",status) '
            'VALUES (gen_random_uuid()::text,$1,$2,$3::jsonb,$4,$5) RETURNING id',
            suite_id, "mock-model", json.dumps({"mock": True}), n, "RUNNING")
        await con.execute(
            'INSERT INTO "Trajectory" (id,"runId","taskCaseId") '
            'SELECT gen_random_uuid()::text, $1, id FROM "TaskCase" WHERE "suiteId"=$2',
            run_id, suite_id)

    print(f"run {run_id} enqueued, watching...")
    start, last = time.perf_counter(), 0
    while True:
        async with pool.acquire() as con:
            done = await con.fetchval(
                'SELECT COUNT(*) FROM "Trajectory" WHERE "runId"=$1 AND status IN (\'SCORED\',\'FAILED\')',
                run_id)
        elapsed = time.perf_counter() - start
        if done != last:
            print(f"{done}/{n}  {done/max(elapsed,1)*60:.0f}/min  {elapsed:.0f}s")
            last = done
        if done >= n:
            break
        await asyncio.sleep(2)

    async with pool.acquire() as con:
        lat = await con.fetch(
            'SELECT "latencyMs" FROM "Trajectory" WHERE "runId"=$1 AND status=\'SCORED\'', run_id)
        cost = await con.fetchval('SELECT SUM("costUsd") FROM "Trajectory" WHERE "runId"=$1', run_id)
    xs = sorted(r["latencyMs"] for r in lat)
    print(f"\nthroughput {n/elapsed*60:.0f}/min over {elapsed:.0f}s")
    print(f"p50 {xs[len(xs)//2]}ms  p95 {xs[int(len(xs)*0.95)]}ms  p99 {xs[int(len(xs)*0.99)]}ms")
    print(f"cost ${cost or 0:.4f}  (${(cost or 0)/n*1000:.4f} per 1k)")

if __name__ == "__main__":
    asyncio.run(main())