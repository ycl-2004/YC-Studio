"""enable vector extension

Revision ID: 0001
Revises:
Create Date: 2026-08-01 15:26:32.600601

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Extensions are database-level objects and are not discovered by autogenerate.
    # Source: https://github.com/pgvector/pgvector#installation
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP EXTENSION IF EXISTS vector")
