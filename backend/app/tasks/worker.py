"""ARQ worker entry point for Stage 1 batch ingestion.

Run with ``arq app.tasks.worker.WorkerSettings``.
"""

from typing import Any

from arq.connections import RedisSettings
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models.source import IngestStatus, Source
from app.db.session import async_session_factory
from app.tasks.ingest_tasks import ingest_source


async def recover_pending_sources(ctx: dict[str, Any]) -> None:
    """Enqueue Sources persisted during a Redis outage before a worker was available."""

    async with async_session_factory() as session:
        source_ids = list(
            await session.scalars(
                select(Source.id).where(Source.ingest_status == IngestStatus.PENDING)
            )
        )
    redis = ctx["redis"]
    for source_id in source_ids:
        await redis.enqueue_job(
            "ingest_source",
            str(source_id),
            _job_id=f"ingest-source:{source_id}",
        )


class WorkerSettings:
    """Configuration consumed by the ARQ CLI and Compose worker service."""

    functions = [ingest_source]
    on_startup = recover_pending_sources
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 4
    max_tries = 1
    job_timeout = 1800
