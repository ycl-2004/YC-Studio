"""Searchable chunks derived from parsed documents."""

from datetime import datetime
from uuid import UUID, uuid4

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    literal_column,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# HNSW build parameters. m controls neighbours per node, ef_construction the search
# width while building: higher means better recall and a slower, larger index.
HNSW_M = 16
HNSW_EF_CONSTRUCTION = 200

# 'simple' does no stemming, which is what Chinese needs and English tolerates. The
# two-argument form is IMMUTABLE, a hard requirement for an index expression.
FULLTEXT_REGCONFIG = "simple"


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
        # Declared here rather than only in migration 0004 so `alembic check` does not
        # report them as drift. Both are created empty by the migration and rebuilt on
        # real data by scripts/build_indexes.py — see Stage 1 Step 7.
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_with={"m": HNSW_M, "ef_construction": HNSW_EF_CONSTRUCTION},
        ),
        Index(
            "ix_chunks_text_gin",
            func.to_tsvector(literal_column(f"'{FULLTEXT_REGCONFIG}'"), literal_column("text")),
            postgresql_using="gin",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    # No index=True here: ix_chunks_collection_document already leads with this column,
    # so a single-column index would be a redundant copy PostgreSQL still has to maintain.
    collection_id: Mapped[UUID] = mapped_column(
        ForeignKey("kb_collections.id", ondelete="CASCADE"),
    )

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        index=True,
    )

    ordinal: Mapped[int] = mapped_column()

    text: Mapped[str] = mapped_column(Text)

    token_count: Mapped[int] = mapped_column()

    # NULL for the rule and template libraries. They are fetched whole by SQL and never
    # ranked by similarity, and a whole rulebook is far longer than the encoder's window
    # — embedding it anyway would store a vector for its first 512 tokens and silently
    # drop the rest. The three columns move together: no vector, no provenance.
    embedding: Mapped[list[float] | None] = mapped_column(VECTOR(768), nullable=True)

    embed_model: Mapped[str | None] = mapped_column(String(200), nullable=True)

    embed_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
