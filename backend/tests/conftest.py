"""Shared fixtures for isolated application and database tests.

The test process disables backend/.env before any app import. Local runs use
Testcontainers; CI can explicitly supply a matched pair of service-container URLs.

References:
- https://docs.sqlalchemy.org/en/20/orm/session_api.html#sqlalchemy.orm.Session.params.join_transaction_mode
- https://www.python-httpx.org/advanced/transports/#asgi-transport
- https://fastapi.tiangolo.com/advanced/testing-events/
- https://testcontainers-python.readthedocs.io/en/latest/modules/postgres/README.html
"""

import os
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

# This must happen before test collection imports any app module. Empty means
# SettingsConfigDict(env_file=None), not "look for a dotenv file elsewhere".
os.environ["YCSTUDIO_ENV_FILE"] = ""

BACKEND_DIR = Path(__file__).resolve().parents[1]
POSTGRES_IMAGE = "pgvector/pgvector:0.8.2-pg16"
REDIS_IMAGE = "redis:7.4.10-alpine"
TEST_DATABASE_URL_VARIABLE = "YCSTUDIO_TEST_DATABASE_URL"
TEST_REDIS_URL_VARIABLE = "YCSTUDIO_TEST_REDIS_URL"


@dataclass(frozen=True)
class TestInfrastructure:
    """Connection details owned exclusively by this pytest process."""

    database_url: str
    redis_url: str


def _run_migrations() -> None:
    """Upgrade the ephemeral test database through the production Alembic path."""

    alembic_config = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    command.upgrade(alembic_config, "head")


def _external_service_urls() -> TestInfrastructure | None:
    """Return explicit CI service URLs, rejecting a partially configured pair."""

    database_url = os.getenv(TEST_DATABASE_URL_VARIABLE)
    redis_url = os.getenv(TEST_REDIS_URL_VARIABLE)

    if bool(database_url) != bool(redis_url):
        raise RuntimeError(
            f"{TEST_DATABASE_URL_VARIABLE} and {TEST_REDIS_URL_VARIABLE} must be set together"
        )

    if database_url and redis_url:
        return TestInfrastructure(database_url=database_url, redis_url=redis_url)

    return None


@pytest.fixture(scope="session")
def test_infrastructure() -> Iterator[TestInfrastructure]:
    """Configure isolated CI services or start local containers, then migrate."""

    external_services = _external_service_urls()
    postgres: PostgresContainer | None = None
    redis: RedisContainer | None = None

    if external_services is None:
        postgres = PostgresContainer(
            image=POSTGRES_IMAGE,
            username="ycstudio_test",
            password="ycstudio_test_password",
            dbname="ycstudio_test",
            driver=None,
        )
        redis = RedisContainer(image=REDIS_IMAGE)

        postgres.start()
        try:
            redis.start()
        except Exception:
            postgres.stop()
            raise

        infrastructure = TestInfrastructure(
            database_url=postgres.get_connection_url(driver="asyncpg"),
            redis_url=(f"redis://{redis.get_container_host_ip()}:{redis.get_exposed_port(6379)}/0"),
        )
    else:
        infrastructure = external_services

    test_environment = {
        "ENVIRONMENT": "test",
        "DEBUG": "false",
        "DATABASE_URL": infrastructure.database_url,
        "REDIS_URL": infrastructure.redis_url,
        "LLM_PROVIDER": "test",
        "LLM_API_KEY": "test-not-a-real-secret",
        "LLM_MODEL": "test-model",
        "LLM_BASE_URL": "http://127.0.0.1",
    }
    previous_environment = {name: os.environ.get(name) for name in test_environment}
    os.environ.update(test_environment)

    try:
        _run_migrations()
        yield infrastructure
    finally:
        for name, previous_value in previous_environment.items():
            if previous_value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = previous_value
        if redis is not None:
            redis.stop()
        if postgres is not None:
            postgres.stop()


@pytest.fixture
async def db_session(
    test_infrastructure: TestInfrastructure,
) -> AsyncIterator[AsyncSession]:
    """Yield a commit-capable session, then roll the entire test back."""

    del test_infrastructure  # Ensures containers and migrations exist before app imports.
    from app.db.models.user import User
    from app.db.session import engine

    count_users = select(func.count()).select_from(User)

    async with engine.connect() as connection:
        outer_transaction = await connection.begin()
        baseline_result = await connection.execute(count_users)
        baseline_count = baseline_result.scalar_one()
        session = AsyncSession(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )

        try:
            yield session
        finally:
            await session.close()
            if outer_transaction.is_active:
                await outer_transaction.rollback()

    try:
        async with engine.connect() as verification_connection:
            final_result = await verification_connection.execute(count_users)
            final_count = final_result.scalar_one()

        assert final_count == baseline_count, (
            "Test database contamination detected: the users table changed after rollback"
        )
    finally:
        # pytest gives each test its own event loop. Never retain an asyncpg
        # connection in the global engine pool after that loop is closed.
        await engine.dispose()


@pytest.fixture
async def application(
    db_session: AsyncSession,
    test_infrastructure: TestInfrastructure,
) -> AsyncIterator[FastAPI]:
    """Create the real app with a transaction-controlled session dependency."""

    del test_infrastructure
    from app.db.session import get_session
    from app.main import create_app

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    test_app = create_app()
    test_app.dependency_overrides[get_session] = override_get_session

    try:
        async with test_app.router.lifespan_context(test_app):
            yield test_app
    finally:
        test_app.dependency_overrides.clear()


@pytest.fixture
async def client(application: FastAPI) -> AsyncIterator[AsyncClient]:
    """Call the ASGI app in-process while its lifespan is active."""

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client
