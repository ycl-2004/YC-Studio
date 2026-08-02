"""Searchable chunks derived from parsed documents."""

from datetime import datetime
from uuid import UUID, uuid4

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Chunk(Base):
    """A chunk of document text and its embedding vector."""

    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "ordinal",
            name="uq_chunks_document_ordinal",
        ),
        Index(
            "ix_chunks_collection_document",
            "collection_id",
            "document_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    collection_id: Mapped[UUID] = mapped_column(
        ForeignKey("kb_collections.id", ondelete="CASCADE"),
        index=True,
    )

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        index=True,
    )

    ordinal: Mapped[int] = mapped_column()

    text: Mapped[str] = mapped_column(Text)

    token_count: Mapped[int] = mapped_column()

    embedding: Mapped[list[float]] = mapped_column(VECTOR(768))

    embed_model: Mapped[str] = mapped_column(String(200))

    embed_version: Mapped[str] = mapped_column(String(50))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
