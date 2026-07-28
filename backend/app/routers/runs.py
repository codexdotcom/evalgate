from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Dataset, EvalResult, EvalRun
from app.schemas import ResultOut, RunCreate, RunOut
from app.services.runner import execute_run

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", response_model=RunOut, status_code=201)
async def create_run(
    payload: RunCreate,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    if await db.get(Dataset, payload.dataset_id) is None:
        raise HTTPException(404, "Dataset not found")
    if payload.scorer not in ("exact_match", "llm_judge"):
        raise HTTPException(422, "scorer must be 'exact_match' or 'llm_judge'")

    run = EvalRun(
        dataset_id=payload.dataset_id,
        model=payload.model or settings.default_model,
        scorer=payload.scorer,
        confidence_threshold=(
            payload.confidence_threshold
            if payload.confidence_threshold is not None
            else settings.default_confidence_threshold
        ),
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    background.add_task(execute_run, run.id)
    return run


@router.get("", response_model=list[RunOut])
async def list_runs(db: AsyncSession = Depends(get_db)):
    return (
        await db.execute(select(EvalRun).order_by(EvalRun.created_at.desc()))
    ).scalars().all()


@router.get("/{run_id}", response_model=RunOut)
async def get_run(run_id: UUID, db: AsyncSession = Depends(get_db)):
    run = await db.get(EvalRun, run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    return run


@router.get("/{run_id}/results", response_model=list[ResultOut])
async def get_results(run_id: UUID, db: AsyncSession = Depends(get_db)):
    return (
        await db.execute(
            select(EvalResult)
            .where(EvalResult.run_id == run_id)
            .order_by(EvalResult.created_at)
        )
    ).scalars().all()