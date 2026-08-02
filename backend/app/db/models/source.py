"""Uploaded source records belonging to a knowledge-base collection."""

import enum
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IngestStatus(enum.StrEnum):
    PENDING = "pending"
    PARSING = "parsing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    COMPLETED = "completed"
    FAILED = "failed"


class Source(Base):
    """The immutable upload fact used for deduplication and ingest tracking."""

    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint(
            "collection_id",
            "content_hash",
            name="uq_sources_collection_content_hash",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    collection_id: Mapped[UUID] = mapped_column(
        ForeignKey("kb_collections.id", ondelete="CASCADE"),
        index=True,
    )

    filename: Mapped[str] = mapped_column(String(200))

    content_hash: Mapped[str] = mapped_column(String(64))

    dir_path: Mapped[str | None] = mapped_column(String(200), nullable=True)

    ingest_status: Mapped[IngestStatus] = mapped_column(
        Enum(
            IngestStatus,
            name="ingest_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=IngestStatus.PENDING,
        server_default=IngestStatus.PENDING.value,
    )

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
