"""Dependency-free liveness and bounded dependency readiness endpoints.

References:
- https://kubernetes.io/docs/concepts/workloads/pods/probes/
- https://fastapi.tiangolo.com/advanced/response-change-status-code/
- https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- https://redis.readthedocs.io/en/latest/examples/asyncio_examples.html
"""

import asyncio
from typing import cast

import structlog
from fastapi import APIRouter, Request, Response, status
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import get_settings
from app.schemas.health import DependencyStatus, HealthResponse, ReadinessResponse

router = APIRouter(tags=["system"])
logger = structlog.stdlib.get_logger(__name__)


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Check whether the API process is alive",
)
async def health() -> HealthResponse:
    """Return process liveness without touching any external dependency."""

    return HealthResponse()


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ReadinessResponse,
            "description": "One or more required dependencies are unavailable.",
        }
    },
    summary="Check whether required dependencies can serve traffic",
)
async def readiness(request: Request, response: Response) -> ReadinessResponse:
    """Probe PostgreSQL and Redis and return one stable readiness contract."""

    timeout_seconds = get_settings().readiness_timeout_seconds
    db_engine = cast(AsyncEngine, request.app.state.db_engine)
    redis_client = cast(Redis, request.app.state.redis)

    postgres_status, redis_status = await asyncio.gather(
        _check_postgres(db_engine, timeout_seconds),
        _check_redis(redis_client, timeout_seconds),
    )
    dependencies: dict[str, DependencyStatus] = {
        "postgres": postgres_status,
        "redis": redis_status,
    }
    failed_dependencies = [
        dependency
        for dependency, dependency_status in dependencies.items()
        if dependency_status == "error"
    ]

    if failed_dependencies:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        logger.warning(
            "readiness.failed",
            failed_dependencies=failed_dependencies,
        )
        return ReadinessResponse(
            status="not_ready",
            dependencies=dependencies,
            failed_dependencies=failed_dependencies,
        )

    return ReadinessResponse(
        status="ready",
        dependencies=dependencies,
    )


async def _check_postgres(engine: AsyncEngine, timeout_seconds: float) -> DependencyStatus:
    """Run a bounded real query without changing database state."""

    try:
        async with asyncio.timeout(timeout_seconds):
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
    except Exception as error:
        logger.warning(
            "readiness.dependency_failed",
            dependency="postgres",
            error_type=type(error).__name__,
        )
        return "error"
    return "ok"


async def _check_redis(redis_client: Redis, timeout_seconds: float) -> DependencyStatus:
    """Run a bounded Redis PING without changing stored data."""

    try:
        async with asyncio.timeout(timeout_seconds):
            ping_succeeded = await redis_client.ping()
            if not ping_succeeded:
                raise RuntimeError("Redis PING returned a false result")
    except Exception as error:
        logger.warning(
            "readiness.dependency_failed",
            dependency="redis",
            error_type=type(error).__name__,
        )
        return "error"
    return "ok"
