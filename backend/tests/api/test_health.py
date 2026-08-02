"""Liveness endpoint contract tests."""

from uuid import UUID

from httpx import AsyncClient


async def test_health_uses_isolated_test_configuration(
    client: AsyncClient,
    test_infrastructure,
) -> None:
    """The real app is alive and cannot inherit development dependency URLs."""

    from app.core.config import SETTINGS_ENV_FILE, get_settings

    response = await client.get("/health")
    settings = get_settings()

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    UUID(response.headers["X-Request-ID"])
    assert SETTINGS_ENV_FILE is None
    assert settings.environment == "test"
    assert settings.database_url == test_infrastructure.database_url
    assert settings.redis_url == test_infrastructure.redis_url
