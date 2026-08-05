"""ORM models for the retrieval evaluation corpus and immutable run history."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EvalDataset(Base):
    """A versioned collection of active and inactive retrieval test cases."""

    __tablename__ = "eval_datasets"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200))
    construction_method: Mapped[str] = mapped_column(String(100))
    version: Mapped[str] = mapped_column(String(50))
    case_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class EvalCase(Base):
    """One query and the chunk ids a correct retriever is expected to return."""

    __tablename__ = "eval_cases"
    __table_args__ = (
        Index("ix_eval_cases_dataset_active", "dataset_id", "is_active"),
        Index("ix_eval_cases_dataset_source", "dataset_id", "source"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    dataset_id: Mapped[UUID] = mapped_column(
        ForeignKey("eval_datasets.id", ondelete="CASCADE"),
        index=True,
    )
    query: Mapped[str] = mapped_column(Text)
    expected_chunk_ids: Mapped[list[str]] = mapped_column(JSONB)
    source: Mapped[str] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    case_metadata: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class EvalRun(Base):
    """One reproducible evaluation execution and its aggregate metrics."""

    __tablename__ = "eval_runs"
    __table_args__ = (
        Index("ix_eval_runs_dataset_created", "dataset_id", "created_at"),
        Index("ix_eval_runs_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    dataset_id: Mapped[UUID] = mapped_column(
        ForeignKey("eval_datasets.id", ondelete="CASCADE"),
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), default="queued", server_default="queued")
    config_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary_metrics: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class EvalResult(Base):
    """Per-case result; kept even when the case is later deactivated."""

    __tablename__ = "eval_results"
    __table_args__ = (
        Index("ix_eval_results_attribution", "attribution"),
        UniqueConstraint("run_id", "case_id", name="uq_eval_results_run_case"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("eval_runs.id", ondelete="CASCADE"),
        index=True,
    )
    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("eval_cases.id"),
        index=True,
    )
    retrieved_chunk_ids: Mapped[list[str]] = mapped_column(JSONB)
    retrieved_document_ids: Mapped[list[str]] = mapped_column(JSONB)
    retrieved_scores: Mapped[list[float]] = mapped_column(JSONB)
    hit_positions: Mapped[list[int]] = mapped_column(JSONB)
    recall_at_k: Mapped[float] = mapped_column()
    mrr: Mapped[float] = mapped_column()
    ndcg_at_k: Mapped[float] = mapped_column()
    attribution: Mapped[str | None] = mapped_column(String(20), nullable=True)
    latency_ms: Mapped[float] = mapped_column()
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
