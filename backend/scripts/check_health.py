"""Verify Stage 8 liveness/readiness with real database fault injection.

Run from backend/ with uv run python scripts/check_health.py, or use make health-check
from the repository root. The script always restores PostgreSQL and Redis in a finally block.

References:
- https://kubernetes.io/docs/concepts/workloads/pods/probes/
- https://www.python-httpx.org/advanced/transports/#asgi-transport
"""

import asyncio
import subprocess
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import UUID

from httpx import ASGITransport, AsyncClient, Response

from app.core.middleware import REQUEST_ID_HEADER
from app.main import create_app

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_COMMAND = [
    "docker",
    "compose",
    "--env-file",
    "backend/.env",
]


def run_compose(*arguments: str) -> None:
    """Run one Compose operation and include full diagnostics on failure."""

    result = subprocess.run(
        [*COMPOSE_COMMAND, *arguments],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"docker compose {' '.join(arguments)} failed with exit {result.returncode}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


async def request_health(client: AsyncClient) -> tuple[Response, float]:
    """Return one liveness response and its in-process ASGI duration."""

    started_at = perf_counter()
    response = await client.get("/health")
    return response, (perf_counter() - started_at) * 1000


def assert_request_id(response: Response) -> None:
    """Require the Step 7 correlation header on an operational response."""

    UUID(response.headers[REQUEST_ID_HEADER])


async def wait_until_ready(client: AsyncClient, timeout_seconds: float = 30.0) -> Response:
    """Poll the same application instance until dependencies recover."""

    deadline = asyncio.get_running_loop().time() + timeout_seconds
    latest_response: Response | None = None
    while asyncio.get_running_loop().time() < deadline:
        latest_response = await client.get("/ready")
        if latest_response.status_code == 200:
            return latest_response
        await asyncio.sleep(0.5)

    latest_body: Any = None if latest_response is None else latest_response.json()
    raise AssertionError(f"/ready did not recover within {timeout_seconds}s: {latest_body}")


async def check_health_contract() -> None:
    """Run healthy, failed-database, liveness, and recovery acceptance checks."""

    await asyncio.to_thread(run_compose, "up", "-d", "--wait", "db", "redis")
    application = create_app()
    transport = ASGITransport(app=application)

    try:
        async with application.router.lifespan_context(application):
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                healthy_response = await client.get("/ready")
                assert healthy_response.status_code == 200
                assert healthy_response.json() == {
                    "status": "ready",
                    "dependencies": {"postgres": "ok", "redis": "ok"},
                    "failed_dependencies": [],
                }
                assert_request_id(healthy_response)
                print("PASS /ready reports healthy PostgreSQL and Redis")

                await asyncio.to_thread(run_compose, "stop", "db")
                unavailable_response = await client.get("/ready")
                assert unavailable_response.status_code == 503
                unavailable_body = unavailable_response.json()
                assert unavailable_body["status"] == "not_ready"
                assert unavailable_body["dependencies"]["postgres"] == "error"
                assert "postgres" in unavailable_body["failed_dependencies"]
                assert_request_id(unavailable_response)
                print("PASS stopped PostgreSQL makes /ready return 503 and identify postgres")

                liveness_durations: list[float] = []
                for _ in range(5):
                    health_response, duration_ms = await request_health(client)
                    assert health_response.status_code == 200
                    assert health_response.json() == {"status": "ok"}
                    assert_request_id(health_response)
                    liveness_durations.append(duration_ms)
                assert max(liveness_durations) < 10.0, liveness_durations
                print(
                    "PASS /health remains 200 without dependencies "
                    f"(max {max(liveness_durations):.3f}ms)"
                )

                await asyncio.to_thread(run_compose, "start", "db")
                recovered_response = await wait_until_ready(client)
                assert recovered_response.json() == {
                    "status": "ready",
                    "dependencies": {"postgres": "ok", "redis": "ok"},
                    "failed_dependencies": [],
                }
                assert_request_id(recovered_response)
                print("PASS /ready recovers after PostgreSQL starts without restarting the app")

                await asyncio.to_thread(run_compose, "stop", "redis")
                redis_unavailable_response = await client.get("/ready")
                assert redis_unavailable_response.status_code == 503
                redis_unavailable_body = redis_unavailable_response.json()
                assert redis_unavailable_body["status"] == "not_ready"
                assert redis_unavailable_body["dependencies"]["redis"] == "error"
                assert "redis" in redis_unavailable_body["failed_dependencies"]
                assert_request_id(redis_unavailable_response)
                print("PASS stopped Redis makes /ready return 503 and identify redis")

                await asyncio.to_thread(run_compose, "start", "redis")
                redis_recovered_response = await wait_until_ready(client)
                assert redis_recovered_response.json() == {
                    "status": "ready",
                    "dependencies": {"postgres": "ok", "redis": "ok"},
                    "failed_dependencies": [],
                }
                assert_request_id(redis_recovered_response)
                print("PASS /ready recovers after Redis starts without restarting the app")
    finally:
        await asyncio.to_thread(run_compose, "up", "-d", "--wait", "db", "redis")

    print("PASS Docker dependencies restored and healthy")
    print("PASS Stage 0 Step 8 health check completed")


if __name__ == "__main__":
    asyncio.run(check_health_contract())
