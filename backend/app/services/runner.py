import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.enums import ReviewStatus, RunStatus, Verdict
from app.models import EvalCase, EvalResult, EvalRun, ReviewItem
from app.scorers import get_scorer
from app.scorers.base import Scorer
from app.services import llm_client

logger = logging.getLogger("evalgate.runner")

UNDER_TEST_SYSTEM = "You are the assistant under evaluation. Answer directly and concisely."


@dataclass
class _Outcome:
    case_id: UUID
    model_output: str
    score: float
    confidence: float
    reasoning: str | None
    errored: bool


def _decide(run: EvalRun, scorer: Scorer, outcome: _Outcome) -> Verdict:
    # An outcome we could not produce is not a failing outcome — the model may
    # well have been right. Escalate rather than record a verdict we did not
    # actually earn.
    if outcome.errored:
        return Verdict.NEEDS_REVIEW
    if not scorer.deterministic and outcome.confidence < run.confidence_threshold:
        return Verdict.NEEDS_REVIEW
    return Verdict.PASS if outcome.score >= settings.pass_threshold else Verdict.FAIL


async def _evaluate(
    case: EvalCase, run: EvalRun, scorer: Scorer, sem: asyncio.Semaphore
) -> _Outcome:
    async with sem:
        try:
            actual = await llm_client.complete(
                run.model, case.input, system=UNDER_TEST_SYSTEM
            )
            sr = await scorer.score(
                input=case.input,
                expected=case.expected_output,
                actual=actual,
            )
            return _Outcome(
                case_id=case.id,
                model_output=actual,
                score=sr.score,
                confidence=sr.confidence,
                reasoning=sr.reasoning,
                errored=False,
            )
        except Exception as exc:
            # One malformed judge response or one rate-limit must not discard
            # the other N-1 cases we already paid for.
            logger.exception("Case %s failed in run %s", case.id, run.id)
            return _Outcome(
                case_id=case.id,
                model_output="",
                score=0.0,
                confidence=0.0,
                reasoning=f"[error] {type(exc).__name__}: {exc}",
                errored=True,
            )


async def execute_run(run_id) -> None:
    async with AsyncSessionLocal() as db:
        run = await db.get(EvalRun, run_id)
        if run is None:
            logger.warning("Run %s vanished before execution", run_id)
            return

        run.status = RunStatus.RUNNING.value
        await db.commit()

        try:
            cases = (
                await db.execute(
                    select(EvalCase)
                    .where(EvalCase.dataset_id == run.dataset_id)
                    # Cases inserted in one commit share a timestamp, so id is
                    # the tiebreaker that keeps ordering stable across queries.
                    .order_by(EvalCase.created_at, EvalCase.id)
                )
            ).scalars().all()
            scorer = get_scorer(run.scorer, model=run.model)
        except Exception:
            logger.exception("Run %s could not start", run_id)
            run.status = RunStatus.FAILED.value
            await db.commit()
            return

        sem = asyncio.Semaphore(max(1, settings.max_concurrency))
        outcomes = await asyncio.gather(
            *(_evaluate(case, run, scorer, sem) for case in cases)
        )

        # The LLM calls fan out, but the writes do not: a single AsyncSession
        # is not safe to use from concurrent tasks.
        for outcome in outcomes:
            verdict = _decide(run, scorer, outcome)
            result = EvalResult(
                run_id=run.id,
                case_id=outcome.case_id,
                model_output=outcome.model_output,
                score=outcome.score,
                confidence=outcome.confidence,
                verdict=verdict.value,
                reasoning=outcome.reasoning,
                scorer=run.scorer,
            )
            db.add(result)
            await db.flush()  # populate result.id

            if verdict == Verdict.NEEDS_REVIEW:
                db.add(
                    ReviewItem(result_id=result.id, status=ReviewStatus.PENDING.value)
                )

        errored = sum(1 for o in outcomes if o.errored)
        # Every single case failing means the run never really happened —
        # usually a bad key or an unreachable model. Say so instead of
        # reporting a tidy queue of "needs review".
        run.status = (
            RunStatus.FAILED.value
            if cases and errored == len(cases)
            else RunStatus.COMPLETED.value
        )
        run.completed_at = datetime.now(timezone.utc)
        await db.commit()
        logger.info(
            "Run %s finished: %d cases, %d errored, status=%s",
            run_id,
            len(cases),
            errored,
            run.status,
        )
