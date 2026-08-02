"""Knowledge base collections: the four-layer library every source belongs to."""

import enum
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CollectionKind(enum.StrEnum):
    """How a library is consumed at retrieval time, not merely what it stores."""

    CASE = "case"
    RULE = "rule"
    TEMPLATE = "template"
    MATERIAL = "material"


class CollectionScope(enum.StrEnum):
    """Public libraries ship with the repo via seed script; private ones belong to a user."""

    PUBLIC = "public"
    PRIVATE = "private"


class Collection(Base):
    """A knowledge base library; every source belongs to exactly one collection."""

    __tablename__ = "kb_collections"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "kind",
            "name",
            name="uq_kb_collections_owner_kind_name",
            # Public collections have user_id NULL. Without this, PostgreSQL treats
            # every NULL as distinct and the seed script could insert the same
            # public library twice.
            postgresql_nulls_not_distinct=True,
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    kind: Mapped[CollectionKind] = mapped_column(
        Enum(
            CollectionKind,
            name="collection_kind",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
    )

    scope: Mapped[CollectionScope] = mapped_column(
        Enum(
            CollectionScope,
            name="collection_scope",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
    )

    name: Mapped[str] = mapped_column(String(200))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
