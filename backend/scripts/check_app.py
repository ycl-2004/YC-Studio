"""Exercise the production FastAPI assembly against real PostgreSQL and Redis.

Run from ``backend/`` with ``uv run python scripts/check_app.py``.

References:
- https://fastapi.tiangolo.com/advanced/testing-events/
- https://www.python-httpx.org/advanced/transports/#asgi-transport
"""

import asyncio

from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import create_app


def check_factory() -> None:
    """The factory must construct distinct FastAPI application instances."""

    first_app = create_app()
    second_app = create_app()
    assert first_app is not second_app
    print("PASS create_app constructs independent application instances")


async def check_lifespan_routes_and_cors() -> None:
    """Run lifespan and verify docs, prefixing, OpenAPI, and configured CORS."""

    settings = get_settings()
    application = create_app()

    transport = ASGITransport(app=application)
    async with application.router.lifespan_context(application):
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            assert application.state.db_engine is not None
            assert application.state.redis is not None
            print("PASS lifespan verified PostgreSQL and Redis")

            docs_response = await client.get("/docs")
            assert docs_response.status_code == 200
            print("PASS /docs is reachable")

            index_response = await client.get(f"{settings.api_prefix}/")
            assert index_response.status_code == 200
            assert index_response.json() == {"name": settings.app_name}
            print(f"PASS {settings.api_prefix}/ is reachable through the aggregate router")

            openapi_response = await client.get("/openapi.json")
            assert openapi_response.status_code == 200
            paths = openapi_response.json()["paths"]
            assert list(paths) == [f"{settings.api_prefix}/"]
            print(
                f"PASS OpenAPI exposes only the expected {settings.api_prefix}/ application route"
            )

            allowed_origin = settings.cors_origins[0]
            cors_response = await client.options(
                f"{settings.api_prefix}/",
                headers={
                    "Origin": allowed_origin,
                    "Access-Control-Request-Method": "GET",
                },
            )
            assert cors_response.status_code == 200
            assert cors_response.headers["access-control-allow-origin"] == allowed_origin
            print("PASS CORS allows an origin loaded from Settings")

    print("PASS lifespan shutdown completed without resource-release errors")


async def main() -> None:
    """Run all Step 6 checks."""

    check_factory()
    await check_lifespan_routes_and_cors()
    print("PASS Stage 0 Step 6 application check completed")


if __name__ == "__main__":
    asyncio.run(main())
