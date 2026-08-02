"""add HNSW and GIN indexes on chunks

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-02

Stage 1 Step 7. The HNSW index serves cosine vector search; the GIN index serves the
BM25-style full-text half of the Stage 3 hybrid retriever.

Creating them here keeps the schema reproducible from migrations alone. Building an
HNSW graph on an empty table is cheap but produces a graph worth nothing, so after a
bulk load run ``uv run python scripts/build_indexes.py`` to rebuild both on real data
and record the build cost.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Keep historical migrations independent from mutable application modules. These
# values intentionally mirror the ORM declaration at the time revision 0004 shipped.
_HNSW_M = 16
_HNSW_EF_CONSTRUCTION = 200
_FULLTEXT_REGCONFIG = "simple"


def upgrade() -> None:
    """Create the HNSW vector index and the GIN full-text index on chunks."""

    op.create_index(
        "ix_chunks_embedding_hnsw",
        "chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
        postgresql_with={"m": _HNSW_M, "ef_construction": _HNSW_EF_CONSTRUCTION},
    )

    op.execute(
        f"""
        CREATE INDEX ix_chunks_text_gin
        ON chunks
        USING gin (to_tsvector('{_FULLTEXT_REGCONFIG}', text))
        """
    )


def downgrade() -> None:
    """Drop both retrieval indexes."""

    op.drop_index("ix_chunks_text_gin", table_name="chunks")
    op.drop_index("ix_chunks_embedding_hnsw", table_name="chunks")
