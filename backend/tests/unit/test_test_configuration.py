"""Tests for the local/CI dependency-selection boundary."""

import pytest
from pytest import MonkeyPatch

from app.core.config import Settings
from tests.conftest import (
    TEST_DATABASE_URL_VARIABLE,
    TEST_REDIS_URL_VARIABLE,
    _external_service_urls,
)


def test_external_service_urls_are_optional(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv(TEST_DATABASE_URL_VARIABLE, raising=False)
    monkeypatch.delenv(TEST_REDIS_URL_VARIABLE, raising=False)

    assert _external_service_urls() is None


def test_external_service_urls_must_be_a_complete_pair(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv(TEST_DATABASE_URL_VARIABLE, "postgresql+asyncpg://test/database")
    monkeypatch.delenv(TEST_REDIS_URL_VARIABLE, raising=False)

    with pytest.raises(RuntimeError, match="must be set together"):
        _external_service_urls()


def test_container_dependency_host_overrides_preserve_url_details() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://user:p%40ss@localhost:5433/ycstudio?ssl=disable",
        database_host_override="db",
        database_port_override=5432,
        redis_url="redis://:secret@localhost:6380/2?protocol=3",
        redis_host_override="redis",
        redis_port_override=6379,
        llm_provider="test",
        llm_api_key="test-not-a-secret",
        llm_model="test-model",
        llm_base_url="http://127.0.0.1",
    )

    assert settings.database_url == (
        "postgresql+asyncpg://user:p%40ss@db:5432/ycstudio?ssl=disable"
    )
    assert settings.redis_url == "redis://:secret@redis:6379/2?protocol=3"
