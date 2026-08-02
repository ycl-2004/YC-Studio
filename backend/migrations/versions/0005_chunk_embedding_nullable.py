"""make chunk embeddings nullable and drop the redundant collection index

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-02

Two corrections to the Stage 1 Step 7 schema.

Rule and template libraries are injected whole and never ranked by similarity, and a
whole rulebook runs far past the encoder's 512-token window — embedding one stored a
vector for its first 512 tokens and silently dropped the rest. Those chunks now carry
NULL for the vector and for its provenance columns.

``ix_chunks_collection_id`` duplicated the leading column of
``ix_chunks_collection_document``, so PostgreSQL maintained two indexes that answer the
same lookup.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import VECTOR

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NULLABLE_COLUMNS: tuple[tuple[str, sa.types.TypeEngine[object]], ...] = (
    ("embedding", VECTOR(768)),
    ("embed_model", sa.String(length=200)),
    ("embed_version", sa.String(length=50)),
)


def upgrade() -> None:
    """Relax the vector columns and drop the duplicate index."""

    for column_name, column_type in _NULLABLE_COLUMNS:
        op.alter_column("chunks", column_name, existing_type=column_type, nullable=True)

    op.drop_index("ix_chunks_collection_id", table_name="chunks")


def downgrade() -> None:
    """Restore NOT NULL and the duplicate index.

    Rows written by the rule and template path hold NULL vectors, so this fails unless
    they are removed first. That is the honest behaviour: the old schema could not
    represent them.
    """

    op.create_index("ix_chunks_collection_id", "chunks", ["collection_id"])

    for column_name, column_type in _NULLABLE_COLUMNS:
        op.alter_column("chunks", column_name, existing_type=column_type, nullable=False)
