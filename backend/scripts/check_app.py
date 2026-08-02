"""Exercise the production FastAPI assembly against real PostgreSQL and Redis.

Run from ``backend/`` with ``uv run python scripts/check_app.py``.

References:
- https://fastapi.tiangolo.com/advanced/testing-events/
- https://www.python-httpx.org/advanced/transports/#asgi-transport
"""

import asyncio
from uuid import UUID

from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.core.middleware import REQUEST_ID_HEADER
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
            UUID(docs_response.headers[REQUEST_ID_HEADER])
            print("PASS /docs is reachable and returns a UUID request ID")

            health_response = await client.get("/health")
            assert health_response.status_code == 200
            assert health_response.json() == {"status": "ok"}
            UUID(health_response.headers[REQUEST_ID_HEADER])
            print("PASS /health is dependency-free and returns a UUID request ID")

            ready_response = await client.get("/ready")
            assert ready_response.status_code == 200
            assert ready_response.json() == {
                "status": "ready",
                "dependencies": {"postgres": "ok", "redis": "ok"},
                "failed_dependencies": [],
            }
            UUID(ready_response.headers[REQUEST_ID_HEADER])
            print("PASS /ready verifies PostgreSQL and Redis")

            allowed_origin = settings.cors_origins[0]
            index_response = await client.get(
                f"{settings.api_prefix}/",
                headers={"Origin": allowed_origin},
            )
            assert index_response.status_code == 200
            assert index_response.json() == {"name": settings.app_name}
            UUID(index_response.headers[REQUEST_ID_HEADER])
            assert index_response.headers["access-control-allow-origin"] == allowed_origin
            exposed_headers = {
                header.strip().lower()
                for header in index_response.headers["access-control-expose-headers"].split(",")
            }
            assert REQUEST_ID_HEADER.lower() in exposed_headers
            print(f"PASS {settings.api_prefix}/ is reachable through the aggregate router")
            print("PASS CORS exposes X-Request-ID to browser clients")

            openapi_response = await client.get("/openapi.json")
            assert openapi_response.status_code == 200
            paths = openapi_response.json()["paths"]
            assert set(paths) == {
                "/health",
                "/ready",
                f"{settings.api_prefix}/",
                f"{settings.api_prefix}/kb/upload",
                f"{settings.api_prefix}/kb/search",
            }
            print("PASS OpenAPI exposes health, API index, and knowledge-base routes")

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
