from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.enums import RunStatus
from app.models import EvalRun, Report
from app.schemas import ReportOut
from app.services.report import generate_report

router = APIRouter(prefix="/runs", tags=["reports"])


@router.post("/{run_id}/report", response_model=ReportOut, status_code=201)
async def create_report(run_id: UUID, db: AsyncSession = Depends(get_db)):
    run = await db.get(EvalRun, run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    if run.status != RunStatus.COMPLETED.value:
        raise HTTPException(400, f"Run is not completed (status: {run.status})")
    return await generate_report(db, run_id)


@router.get("/{run_id}/report", response_model=ReportOut)
async def get_report(run_id: UUID, db: AsyncSession = Depends(get_db)):
    report = (
        await db.execute(
            select(Report)
            .where(Report.run_id == run_id)
            .order_by(Report.generated_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if report is None:
        raise HTTPException(404, "No report for this run")
    return report