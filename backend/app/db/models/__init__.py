"""Import ORM models here so Alembic can discover their metadata."""

from app.db.models.user import User

__all__ = ["User"]
