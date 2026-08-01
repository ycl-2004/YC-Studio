"""Repeatable Stage 0 Step 5 checks against the migrated development database."""

import asyncio
from pathlib import Path
from uuid import UUID, uuid4

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import DateTime, String, Uuid, func, inspect, select, text
from sqlalchemy.engine import Connection
from sqlalchemy.engine.interfaces import (
    ReflectedColumn,
    ReflectedPrimaryKeyConstraint,
    ReflectedUniqueConstraint,
)
from sqlalchemy.exc import IntegrityError

from ycstudio.db.models import User
from ycstudio.db.session import async_session_factory, engine

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_EMAIL_DOMAIN = "example.invalid"


def inspect_users_schema(
    connection: Connection,
) -> tuple[
    list[ReflectedColumn],
    ReflectedPrimaryKeyConstraint,
    list[ReflectedUniqueConstraint],
]:
    """Inspect the users table through SQLAlchemy's synchronous Inspector API."""

    inspector = inspect(connection)
    return (
        inspector.get_columns(User.__tablename__),
        inspector.get_pk_constraint(User.__tablename__),
        inspector.get_unique_constraints(User.__tablename__),
    )


def get_code_head() -> str:
    """Return the single revision at the head of the local migration graph."""

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    head = ScriptDirectory.from_config(config).get_current_head()
    assert head is not None
    return head


async def check_revision_and_extension() -> None:
    """Verify that the database is at code head and pgvector is available."""

    async with engine.connect() as connection:
        database_revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
        vector_version = await connection.scalar(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        )

    code_head = get_code_head()
    assert database_revision == code_head
    assert vector_version is not None
    print(f"[1/4] database revision {database_revision} matches head; vector {vector_version}: ok")


async def check_users_schema() -> None:
    """Verify the users columns, primary key, and unique email constraint."""

    async with engine.connect() as connection:
        columns, primary_key, unique_constraints = await connection.run_sync(inspect_users_schema)

    columns_by_name = {column["name"]: column for column in columns}
    assert set(columns_by_name) == {"id", "email", "created_at", "updated_at"}
    assert all(not column["nullable"] for column in columns_by_name.values())

    id_type = columns_by_name["id"]["type"]
    email_type = columns_by_name["email"]["type"]
    created_at_type = columns_by_name["created_at"]["type"]
    updated_at_type = columns_by_name["updated_at"]["type"]

    assert isinstance(id_type, Uuid)
    assert isinstance(email_type, String) and email_type.length == 320
    assert isinstance(created_at_type, DateTime) and created_at_type.timezone
    assert isinstance(updated_at_type, DateTime) and updated_at_type.timezone
    assert primary_key["constrained_columns"] == ["id"]
    assert any(constraint["column_names"] == ["email"] for constraint in unique_constraints)
    print("[2/4] users columns, primary key, and unique email constraint: ok")


async def check_user_round_trip_with_rollback(email: str) -> None:
    """Flush and read a real ORM row, then roll it back so no fixture persists."""

    async with async_session_factory() as session:
        try:
            user = User(email=email)
            session.add(user)
            await session.flush()

            loaded_user = await session.scalar(select(User).where(User.email == email))
            assert loaded_user is not None
            assert loaded_user.id == user.id
            assert isinstance(user.id, UUID)
            assert user.created_at.tzinfo is not None
            assert user.updated_at.tzinfo is not None
        finally:
            await session.rollback()

    print("[3/4] real User insert/read round trip rolled back cleanly: ok")


async def check_unique_email_and_cleanup(duplicate_email: str, round_trip_email: str) -> None:
    """Prove PostgreSQL rejects duplicate emails and both probes leave zero rows."""

    async with async_session_factory() as session:
        session.add_all([User(email=duplicate_email), User(email=duplicate_email)])
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
        else:
            await session.rollback()
            raise AssertionError("users.email accepted duplicate values")

    async with async_session_factory() as session:
        remaining_rows = await session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.email.in_([round_trip_email, duplicate_email]))
        )

    assert remaining_rows == 0
    print("[4/4] duplicate email rejected; migration probe rows remaining: 0")


async def main() -> None:
    """Run all Stage 0 Step 5 migration checks."""

    run_id = uuid4().hex
    round_trip_email = f"stage0-step5-roundtrip-{run_id}@{TEST_EMAIL_DOMAIN}"
    duplicate_email = f"stage0-step5-duplicate-{run_id}@{TEST_EMAIL_DOMAIN}"

    try:
        await check_revision_and_extension()
        await check_users_schema()
        await check_user_round_trip_with_rollback(round_trip_email)
        await check_unique_email_and_cleanup(duplicate_email, round_trip_email)
    finally:
        await engine.dispose()

    print("Stage 0 Step 5 migration checks passed; no probe rows persisted.")


if __name__ == "__main__":
    asyncio.run(main())
