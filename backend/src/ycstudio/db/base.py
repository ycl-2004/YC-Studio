"""Shared declarative base for all YC Studio ORM models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class inherited by every SQLAlchemy ORM model."""
