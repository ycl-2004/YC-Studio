"""Stage 1 upload and vector-retrieval HTTP endpoints.

References:
- https://fastapi.tiangolo.com/tutorial/request-forms-and-files/
- https://github.com/pgvector/pgvector-python#sqlalchemy
"""

from pathlib import Path
from typing import Annotated
from uuid import UUID

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.storage import LocalUploadStorage
from app.api.deps import get_current_user_id
from app.core.config import get_settings
from app.db.models.collection import CollectionKind
from app.db.session import get_session
from app.rag.parsers.factory import ParserFactory
from app.schemas.kb import (
    BatchProgressResponse,
    BatchUploadResponse,
    SearchDocument,
    SearchRequest,
    SearchResponse,
    SearchResult,
    SearchSource,
    UploadResponse,
)
from app.services.kb_service import (
    CollectionAccessError,
    CollectionKindMismatchError,
    CollectionNotFoundError,
    PendingUpload,
    UnsupportedSearchKindError,
    create_pending_batch,
    get_batch_progress,
    ingest_private_upload,
    search_chunks,
)

router = APIRouter(prefix="/kb", tags=["knowledge-base"])

# Clients that cannot determine a type send this; the suffix has already selected the
# parser, and a client-supplied content type is never a security boundary on its own.
_UNKNOWN_MIME_TYPE = "application/octet-stream"
_MARKDOWN_MIME_TYPES = frozenset({"text/markdown", "text/x-markdown", "text/plain"})
_MIME_TYPES_BY_SUFFIX: dict[str, frozenset[str]] = {
    ".md": _MARKDOWN_MIME_TYPES,
    ".markdown": _MARKDOWN_MIME_TYPES,
    ".txt": frozenset({"text/plain"}),
    ".htm": frozenset({"text/html"}),
    ".html": frozenset({"text/html"}),
    ".pdf": frozenset({"application/pdf"}),
    ".docx": frozenset({"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}),
}
_READ_CHUNK_BYTES = 1_048_576


def _assert_every_parsed_suffix_has_mime_types() -> None:
    """Fail at import instead of rejecting a parsable upload with an empty expected set.

    ``ParserFactory`` is the single source of truth for what can be parsed.  Registering a
    parser without listing its content types would otherwise make that format permanently
    unuploadable, so the mismatch is raised here rather than discovered by a user.
    """

    unmapped = sorted(set(ParserFactory.supported_suffixes()) - set(_MIME_TYPES_BY_SUFFIX))
    if unmapped:
        raise RuntimeError(
            f"Parsable suffixes without an upload content-type mapping: {', '.join(unmapped)}. "
            "Add them to _MIME_TYPES_BY_SUFFIX."
        )


_assert_every_parsed_suffix_has_mime_types()


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Synchronously ingest one file into an owned private collection",
)
async def upload_file(
    file: Annotated[UploadFile, File(description="One Markdown, text, PDF, or DOCX file")],
    collection_id: Annotated[UUID, Form()],
    kind: Annotated[CollectionKind, Form()],
    platform: Annotated[str, Form(min_length=1, max_length=100)],
    content_type: Annotated[str, Form(min_length=1, max_length=100)],
    current_user_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UploadResponse:
    """Validate form/file input, enforce ownership, then run the existing ingest service."""

    filename = _validate_upload_metadata(file)
    file_bytes = await _read_limited_upload(file)

    try:
        result = await ingest_private_upload(
            session,
            current_user_id=current_user_id,
            collection_id=collection_id,
            kind=kind,
            filename=filename,
            file_bytes=file_bytes,
            metadata={"platform": platform, "content_type": content_type},
        )
    except CollectionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except CollectionAccessError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except CollectionKindMismatchError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error

    return UploadResponse(
        source_id=result.source_id,
        document_id=result.document_id,
        chunk_count=result.chunk_count,
        skipped=result.skipped,
    )


@router.post(
    "/batch-upload",
    response_model=BatchUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Persist and enqueue many files without waiting for ingestion",
)
async def upload_batch(
    files: Annotated[list[UploadFile], File(description="One or more supported files")],
    collection_id: Annotated[UUID, Form()],
    kind: Annotated[CollectionKind, Form()],
    platform: Annotated[str, Form(min_length=1, max_length=100)],
    content_type: Annotated[str, Form(min_length=1, max_length=100)],
    current_user_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
    dir_paths: Annotated[list[str] | None, Form()] = None,
) -> BatchUploadResponse:
    """Durably save uploaded bytes and Source rows, then enqueue one ARQ job per Source."""

    if not files:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="At least one file is required.",
        )
    if dir_paths is not None and len(dir_paths) != len(files):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="dir_paths must have exactly one entry for every uploaded file.",
        )

    uploads = [
        PendingUpload(
            filename=_validate_upload_metadata(file),
            file_bytes=await _read_limited_upload(file),
            dir_path=None if dir_paths is None else dir_paths[index],
        )
        for index, file in enumerate(files)
    ]
    storage = LocalUploadStorage()
    persisted_source_ids: list[UUID] = []
    try:
        batch, sources = await create_pending_batch(
            session,
            current_user_id=current_user_id,
            collection_id=collection_id,
            kind=kind,
            metadata={"platform": platform, "content_type": content_type},
            uploads=uploads,
        )
        for source, upload in zip(sources, uploads, strict=True):
            await storage.save(source.id, source.filename, upload.file_bytes)
            persisted_source_ids.append(source.id)
        await session.commit()
    except CollectionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except CollectionAccessError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except (CollectionKindMismatchError, ValueError) as error:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    except Exception:
        await session.rollback()
        raise

    try:
        await _enqueue_sources(persisted_source_ids)
    except Exception as error:
        # The durable records stay pending; worker startup recovers them once Redis returns.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Files were saved but could not be queued; the worker will recover pending files."
            ),
        ) from error

    return BatchUploadResponse(
        batch_id=batch.id, source_ids=persisted_source_ids, total=len(sources)
    )


@router.get(
    "/batches/{batch_id}",
    response_model=BatchProgressResponse,
    summary="Get asynchronous ingestion progress for one batch",
)
async def batch_progress(
    batch_id: UUID,
    current_user_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BatchProgressResponse:
    """Report persistent Source counters, independent of ARQ's transient job-result TTL."""

    try:
        progress = await get_batch_progress(
            session,
            current_user_id=current_user_id,
            batch_id=batch_id,
        )
    except CollectionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except CollectionAccessError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    return BatchProgressResponse(
        batch_id=progress.batch_id,
        total=progress.total,
        completed=progress.completed,
        failed=progress.failed,
        in_progress=progress.in_progress,
        pending=progress.pending,
    )


@router.post(
    "/search",
    response_model=SearchResponse,
    summary="Search case or material chunks and return their original document/source",
)
async def search_knowledge_base(
    request: SearchRequest,
    current_user_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SearchResponse:
    """Run the Stage 1 vector-search path and expose a normalized similarity score."""

    try:
        retrieved_chunks = await search_chunks(
            session,
            current_user_id=current_user_id,
            request=request,
        )
    except UnsupportedSearchKindError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error

    return SearchResponse(
        results=[
            SearchResult(
                chunk_id=retrieved.chunk.id,
                text=retrieved.chunk.text,
                score=retrieved.score,
                document=SearchDocument(
                    id=retrieved.document.id,
                    title=retrieved.document.title,
                ),
                source=SearchSource(
                    id=retrieved.source.id,
                    filename=retrieved.source.filename,
                ),
            )
            for retrieved in retrieved_chunks
        ]
    )


def _validate_upload_metadata(file: UploadFile) -> str:
    """Reject missing/unsupported suffixes and content types before parser dispatch."""

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="An uploaded filename is required.",
        )

    filename = Path(file.filename).name
    suffix = Path(filename).suffix.casefold()
    supported_suffixes = ParserFactory.supported_suffixes()
    if suffix not in supported_suffixes:
        supported_formats = ", ".join(supported_suffixes)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"Unsupported file type {suffix or '(no extension)'}. "
                f"Supported formats: {supported_formats}."
            ),
        )

    allowed_mime_types = _MIME_TYPES_BY_SUFFIX[suffix]
    if file.content_type not in allowed_mime_types | {_UNKNOWN_MIME_TYPE}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"Content type {file.content_type!r} is not valid for {suffix}. "
                f"Expected one of: {', '.join(sorted(allowed_mime_types))}."
            ),
        )
    return filename


async def _read_limited_upload(file: UploadFile) -> bytes:
    """Read the stream in bounded chunks and stop before accepting an oversized file."""

    limit = get_settings().upload_max_bytes
    data = bytearray()
    while chunk := await file.read(_READ_CHUNK_BYTES):
        data.extend(chunk)
        if len(data) > limit:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"File exceeds the {limit}-byte upload limit.",
            )
    return bytes(data)


async def _enqueue_sources(source_ids: list[UUID]) -> None:
    """Use one short-lived ARQ connection to enqueue durable source identifiers only."""

    redis = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    try:
        for source_id in source_ids:
            await redis.enqueue_job(
                "ingest_source",
                str(source_id),
                _job_id=f"ingest-source:{source_id}",
            )
    finally:
        await redis.aclose()
