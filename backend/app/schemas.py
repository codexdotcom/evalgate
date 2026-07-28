from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.enums import Verdict


# ---------- Datasets ----------
class EvalCaseCreate(BaseModel):
    input: str
    expected_output: str
    metadata: Optional[dict[str, Any]] = None


class EvalCaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    input: str
    expected_output: str
    metadata: Optional[dict[str, Any]] = Field(
        default=None, validation_alias="case_metadata"
    )
    created_at: datetime


class DatasetCreate(BaseModel):
    name: str
    description: Optional[str] = None
    cases: list[EvalCaseCreate] = Field(default_factory=list)


class DatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: Optional[str] = None
    created_at: datetime
    case_count: Optional[int] = None


class DatasetDetail(DatasetOut):
    cases: list[EvalCaseOut] = Field(default_factory=list)


# ---------- Runs ----------
class RunCreate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    dataset_id: uuid.UUID
    model: Optional[str] = None
    scorer: str = "llm_judge"  # "exact_match" | "llm_judge"
    confidence_threshold: Optional[float] = None


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: uuid.UUID
    dataset_id: uuid.UUID
    model: str
    scorer: str
    confidence_threshold: float
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None


class ResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: uuid.UUID
    run_id: uuid.UUID
    case_id: uuid.UUID
    model_output: str
    score: float
    confidence: float
    verdict: str
    reasoning: Optional[str] = None
    scorer: str
    created_at: datetime


# ---------- Review ----------
class ReviewDetailOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: uuid.UUID
    result_id: uuid.UUID
    status: str
    human_verdict: Optional[str] = None
    reviewer: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    resolved_at: Optional[datetime] = None
    # embedded context for the reviewer
    input: str
    expected_output: str
    model_output: str
    score: float
    confidence: float
    reasoning: Optional[str] = None


class ReviewItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    result_id: uuid.UUID
    status: str
    human_verdict: Optional[str] = None
    reviewer: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    resolved_at: Optional[datetime] = None


class ReviewResolve(BaseModel):
    verdict: Verdict  # only pass/fail accepted (validated in the router)
    reviewer: str
    notes: Optional[str] = None


# ---------- Reports ----------
class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    summary: dict[str, Any]
    content_hash: str
    generated_at: datetime