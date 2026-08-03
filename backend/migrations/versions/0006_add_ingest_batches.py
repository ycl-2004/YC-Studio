"""add durable batch upload records

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create batch records and attach optional source ownership to them."""

    op.create_table(
        "ingest_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["collection_id"], ["kb_collections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ingest_batches_collection_id", "ingest_batches", ["collection_id"])
    op.create_index("ix_ingest_batches_user_id", "ingest_batches", ["user_id"])
    op.add_column("sources", sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_sources_batch_id_ingest_batches",
        "sources",
        "ingest_batches",
        ["batch_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_sources_batch_id", "sources", ["batch_id"])


def downgrade() -> None:
    """Remove the optional batch tracking structures."""

    op.drop_index("ix_sources_batch_id", table_name="sources")
    op.drop_constraint("fk_sources_batch_id_ingest_batches", "sources", type_="foreignkey")
    op.drop_column("sources", "batch_id")
    op.drop_index("ix_ingest_batches_user_id", table_name="ingest_batches")
    op.drop_index("ix_ingest_batches_collection_id", table_name="ingest_batches")
    op.drop_table("ingest_batches")
