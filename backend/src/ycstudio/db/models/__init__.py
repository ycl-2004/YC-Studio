"""Import ORM models here so Alembic can discover their metadata."""

from ycstudio.db.models.user import User

__all__ = ["User"]
