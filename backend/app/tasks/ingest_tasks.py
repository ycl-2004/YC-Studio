"""ARQ jobs for durable, per-source background ingestion."""

from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import update

from app.adapters.storage import LocalUploadStorage
from app.db.models.collection import Collection
from app.db.models.ingest_batch import IngestBatch
from app.db.models.source import IngestStatus, Source
from app.db.session import async_session_factory
from app.services.ingest_service import ingest_pending_source

logger = structlog.stdlib.get_logger(__name__)


async def ingest_source(ctx: dict[str, Any], source_id: str) -> dict[str, str | int | bool]:
    """Ingest one durable Source; failures are isolated to that source's status record.

    Every ``Source.id`` reference below is the plain ``parsed_source_id`` UUID, never the
    ORM attribute ``source.id``. ``ingest_pending_source`` rolls back to a savepoint on
    failure, which expires ``source``; a later ``source.id`` access would then try a
    synchronous lazy-load outside of any greenlet context and raise ``MissingGreenlet``
    instead of the exception actually worth recording — turning a normal ingest failure
    (a missing model, a bad file) into an unrelated crash with no ``failed`` status and
    no error message. See app/services/ingest_service.py for the same fix.
    """

    del ctx
    parsed_source_id = UUID(source_id)
    async with async_session_factory() as session:
        source = await session.get(Source, parsed_source_id)
        if source is None:
            return {"source_id": source_id, "skipped": True, "reason": "source_missing"}
        if source.ingest_status is not IngestStatus.PENDING:
            return {"source_id": source_id, "skipped": True, "reason": source.ingest_status.value}

        batch = await session.get(IngestBatch, source.batch_id)
        collection = await session.get(Collection, source.collection_id)
        if batch is None or collection is None:
            await session.execute(
                update(Source)
                .where(Source.id == parsed_source_id)
                .values(
                    ingest_status=IngestStatus.FAILED,
                    error_message="Batch or collection is no longer available.",
                )
            )
            await session.commit()
            return {"source_id": source_id, "skipped": False, "failed": True}

        try:
            content = await LocalUploadStorage().read(source.id, source.filename)
            result = await ingest_pending_source(
                session,
                source=source,
                collection=collection,
                file_bytes=content,
                metadata=batch.upload_metadata,
            )
        except Exception as error:
            await session.execute(
                update(Source)
                .where(Source.id == parsed_source_id)
                .values(
                    ingest_status=IngestStatus.FAILED,
                    error_message=str(error)[:500],
                )
            )
            await session.commit()
            logger.warning(
                "batch_ingest.source_failed",
                source_id=source_id,
                error_type=type(error).__name__,
            )
            return {"source_id": source_id, "skipped": False, "failed": True}

        await session.commit()
        return {
            "source_id": source_id,
            "document_id": str(result.document_id) if result.document_id else "",
            "chunk_count": result.chunk_count,
            "skipped": result.skipped,
        }
