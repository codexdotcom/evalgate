import hashlib
import json

from sqlalchemy import func, select

from app.config import settings
from app.enums import ReviewStatus
from app.models import EvalResult, EvalRun, Report, ReviewItem


def compute_content_hash(run, results, summary: dict) -> str:
    """Hash a run's verdicts into a tamper-evident digest.

    Deliberately independent of the order `results` arrives in: they are all
    written inside one transaction and therefore share a created_at, so
    Postgres is free to hand them back in any order it likes. Ordering the
    payload by case_id is what makes "the hash changed" mean "a verdict
    changed" rather than "the planner picked a different scan".
    """
    payload = {
        "run_id": str(run.id),
        "dataset_id": str(run.dataset_id),
        "model": run.model,
        "scorer": run.scorer,
        "confidence_threshold": run.confidence_threshold,
        "pass_threshold": settings.pass_threshold,
        "results": sorted(
            (
                {
                    "case_id": str(r.case_id),
                    "verdict": r.verdict,
                    "score": r.score,
                    "confidence": r.confidence,
                }
                for r in results
            ),
            key=lambda r: r["case_id"],
        ),
        "summary": summary,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


async def generate_report(db, run_id) -> Report:
    """Freeze a run into an auditable pass/fail record.

    The report is reproducible: regenerating it over unchanged results yields
    the same content_hash, so a changed hash means the underlying verdicts
    moved.
    """
    run = await db.get(EvalRun, run_id)
    results = (
        await db.execute(select(EvalResult).where(EvalResult.run_id == run_id))
    ).scalars().all()

    # How many verdicts a human signed off on, for the audit trail.
    reviewed = (
        await db.execute(
            select(func.count(ReviewItem.id))
            .join(EvalResult, ReviewItem.result_id == EvalResult.id)
            .where(
                EvalResult.run_id == run_id,
                ReviewItem.status == ReviewStatus.RESOLVED.value,
            )
        )
    ).scalar_one()

    counts = {"total": len(results), "pass": 0, "fail": 0, "needs_review": 0}
    for r in results:
        counts[r.verdict] = counts.get(r.verdict, 0) + 1

    total = counts["total"]
    decided = counts["pass"] + counts["fail"]
    counts["pass_rate"] = round(counts["pass"] / total, 4) if total else 0.0
    counts["decided_pass_rate"] = round(counts["pass"] / decided, 4) if decided else 0.0
    counts["human_reviewed"] = reviewed

    # The gate itself. An unresolved review item is not a soft signal: the
    # system is explicitly saying it could not decide, so it cannot certify.
    if counts["needs_review"] > 0:
        gate = "blocked"
    elif total == 0:
        gate = "fail"
    else:
        gate = "pass" if counts["pass_rate"] >= settings.gate_pass_rate else "fail"

    counts["gate"] = gate
    counts["gate_pass_rate"] = settings.gate_pass_rate

    content_hash = compute_content_hash(run, results, counts)

    report = Report(run_id=run_id, summary=counts, content_hash=content_hash)
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return report
