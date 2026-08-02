"""FastAPI application assembly and external-resource lifecycle.

References:
- https://fastapi.tiangolo.com/advanced/events/
- https://fastapi.tiangolo.com/tutorial/bigger-applications/
- https://fastapi.tiangolo.com/tutorial/cors/
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from sqlalchemy import text

from app.api import api_router
from app.core.config import get_settings
from app.db.session import engine

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Verify external resources at startup and release their pools at shutdown."""

    settings = get_settings()
    redis_client: Redis | None = None

    try:
        logger.info("Startup: connecting to PostgreSQL")
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        application.state.db_engine = engine
        logger.info("Startup: PostgreSQL connection verified")

        logger.info("Startup: connecting to Redis")
        redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
        await redis_client.ping()
        application.state.redis = redis_client
        logger.info("Startup: Redis connection verified")

        yield
    finally:
        if redis_client is not None:
            logger.info("Shutdown: closing Redis connection pool")
            await redis_client.aclose()
            logger.info("Shutdown: Redis connection pool closed")

        logger.info("Shutdown: disposing PostgreSQL connection pool")
        await engine.dispose()
        logger.info("Shutdown: PostgreSQL connection pool disposed")


def create_app() -> FastAPI:
    """Construct one configured application instance."""

    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(api_router, prefix=settings.api_prefix)
    return application


app = create_app()
