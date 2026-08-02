"""Tests for the local/CI dependency-selection boundary."""

import pytest
from pytest import MonkeyPatch

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
