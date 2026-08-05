"""HTTP contracts for evaluation datasets, runs, and comparisons."""

import enum
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class EvalCaseSource(enum.StrEnum):
    SYNTHETIC = "synthetic"
    MANUAL = "manual"


class EvalRunStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class DatasetCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    version: str = Field(default="v1", min_length=1, max_length=50)
    construction_method: str = Field(default="synthetic_plus_manual", max_length=100)


class ManualCaseInput(BaseModel):
    query: str = Field(min_length=1, max_length=2_000)
    expected_chunk_ids: list[UUID] = Field(min_length=1)
    review_note: str | None = Field(default=None, max_length=2_000)


class ManualCasesRequest(BaseModel):
    cases: list[ManualCaseInput] = Field(min_length=1, max_length=100)


class SyntheticGenerationRequest(BaseModel):
    count: int = Field(default=50, ge=1, le=80)
    seed: int = Field(default=0, ge=0)
    mode: str = Field(default="http", pattern="^(http|offline)$")


class ReviewCaseRequest(BaseModel):
    is_active: bool
    review_note: str | None = Field(default=None, max_length=2_000)


class DatasetStatsResponse(BaseModel):
    total: int
    active: int
    synthetic_total: int
    synthetic_active: int
    manual_active: int
    synthetic_retention_rate: float


class EvalDatasetResponse(BaseModel):
    id: UUID
    name: str
    version: str
    construction_method: str
    case_count: int
    created_at: datetime
    updated_at: datetime
    stats: DatasetStatsResponse


class EvalCaseResponse(BaseModel):
    id: UUID
    dataset_id: UUID
    query: str
    expected_chunk_ids: list[UUID]
    source: EvalCaseSource
    is_active: bool
    review_note: str | None
    created_at: datetime


class SyntheticGenerationAccepted(BaseModel):
    dataset_id: UUID
    status: str
    count: int


class EvalRunCreateRequest(BaseModel):
    dataset_id: UUID
    config_overrides: dict[str, Any] = Field(default_factory=dict)


class EvalRunAccepted(BaseModel):
    run_id: UUID
    status: EvalRunStatus


class EvalRunResponse(BaseModel):
    id: UUID
    dataset_id: UUID
    status: EvalRunStatus
    config_snapshot: dict[str, Any]
    started_at: datetime | None
    finished_at: datetime | None
    summary_metrics: dict[str, Any] | None
    error_message: str | None
    created_at: datetime


class EvalRunListResponse(BaseModel):
    runs: list[EvalRunResponse]


class EvalCompareResponse(BaseModel):
    baseline_run_id: UUID
    current_run_id: UUID
    baseline_summary: dict[str, Any]
    current_summary: dict[str, Any]
    config_diff: dict[str, dict[str, Any]]
    case_diffs: list[dict[str, Any]]
    improved_cases: list[dict[str, Any]]
    regressed_cases: list[dict[str, Any]]
