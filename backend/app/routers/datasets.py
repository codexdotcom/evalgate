from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Dataset, EvalCase
from app.schemas import DatasetCreate, DatasetDetail, DatasetOut

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.post("", response_model=DatasetDetail, status_code=201)
async def create_dataset(payload: DatasetCreate, db: AsyncSession = Depends(get_db)):
    ds = Dataset(name=payload.name, description=payload.description)
    for c in payload.cases:
        ds.cases.append(
            EvalCase(
                input=c.input,
                expected_output=c.expected_output,
                case_metadata=c.metadata,
            )
        )
    db.add(ds)
    await db.commit()

    ds = (
        await db.execute(
            select(Dataset).options(selectinload(Dataset.cases)).where(Dataset.id == ds.id)
        )
    ).scalar_one()
    return ds


@router.get("", response_model=list[DatasetOut])
async def list_datasets(db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(Dataset, func.count(EvalCase.id))
            .outerjoin(EvalCase, EvalCase.dataset_id == Dataset.id)
            .group_by(Dataset.id)
            .order_by(Dataset.created_at.desc())
        )
    ).all()

    out = []
    for ds, count in rows:
        d = DatasetOut.model_validate(ds)
        d.case_count = count
        out.append(d)
    return out


@router.get("/{dataset_id}", response_model=DatasetDetail)
async def get_dataset(dataset_id: UUID, db: AsyncSession = Depends(get_db)):
    ds = (
        await db.execute(
            select(Dataset).options(selectinload(Dataset.cases)).where(Dataset.id == dataset_id)
        )
    ).scalar_one_or_none()
    if ds is None:
        raise HTTPException(404, "Dataset not found")
    return ds