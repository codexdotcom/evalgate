from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.enums import ReviewStatus, Verdict
from app.models import EvalCase, EvalResult, ReviewItem
from app.schemas import ReviewDetailOut, ReviewItemOut, ReviewResolve

router = APIRouter(prefix="/review", tags=["review"])


@router.get("", response_model=list[ReviewDetailOut])
async def list_review(
    status: str = Query(default="pending"),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(ReviewItem, EvalResult, EvalCase)
        .join(EvalResult, ReviewItem.result_id == EvalResult.id)
        .join(EvalCase, EvalResult.case_id == EvalCase.id)
        .order_by(ReviewItem.created_at)
    )
    if status != "all":
        stmt = stmt.where(ReviewItem.status == status)

    rows = (await db.execute(stmt)).all()
    return [
        ReviewDetailOut(
            id=item.id,
            result_id=item.result_id,
            status=item.status,
            human_verdict=item.human_verdict,
            reviewer=item.reviewer,
            notes=item.notes,
            created_at=item.created_at,
            resolved_at=item.resolved_at,
            input=case.input,
            expected_output=case.expected_output,
            model_output=res.model_output,
            score=res.score,
            confidence=res.confidence,
            reasoning=res.reasoning,
        )
        for item, res, case in rows
    ]


@router.post("/{review_id}/resolve", response_model=ReviewItemOut)
async def resolve_review(
    review_id: UUID,
    payload: ReviewResolve,
    db: AsyncSession = Depends(get_db),
):
    item = await db.get(ReviewItem, review_id)
    if item is None:
        raise HTTPException(404, "Review item not found")
    if item.status == ReviewStatus.RESOLVED.value:
        raise HTTPException(400, "Review item already resolved")
    if payload.verdict not in (Verdict.PASS, Verdict.FAIL):
        raise HTTPException(422, "verdict must be 'pass' or 'fail'")

    item.human_verdict = payload.verdict.value
    item.reviewer = payload.reviewer
    item.notes = payload.notes
    item.status = ReviewStatus.RESOLVED.value
    item.resolved_at = datetime.now(timezone.utc)

    # Human decision overrides the machine verdict; append to the audit trail.
    result = await db.get(EvalResult, item.result_id)
    result.verdict = payload.verdict.value
    result.reasoning = (
        (result.reasoning or "")
        + f"\n[human-review] {payload.reviewer}: {payload.verdict.value}"
    )

    await db.commit()
    await db.refresh(item)
    return item