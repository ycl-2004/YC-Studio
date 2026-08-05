"""Stage 1 upload and vector-retrieval HTTP endpoints.

References:
- https://fastapi.tiangolo.com/tutorial/request-forms-and-files/
- https://github.com/pgvector/pgvector-python#sqlalchemy
"""

from pathlib import Path
from typing import Annotated
from uuid import UUID

import structlog
from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.storage import LocalUploadStorage
from app.api.deps import get_current_user_id
from app.core.config import get_settings
from app.db.models.collection import CollectionKind, CollectionScope
from app.db.session import get_session
from app.rag.parsers.factory import ParserFactory
from app.schemas.kb import (
    BatchProgressResponse,
    BatchUploadResponse,
    CollectionListResponse,
    CollectionResponse,
    CollectionSummary,
    CreateCollectionRequest,
    SearchDocument,
    SearchRequest,
    SearchResponse,
    SearchResult,
    SearchSource,
    SourceChunkPreview,
    SourceListResponse,
    SourcePreviewMode,
    SourcePreviewResponse,
    SourceSummary,
    UploadResponse,
)
from app.services.kb_service import (
    CollectionAccessError,
    CollectionAlreadyExistsError,
    CollectionKindMismatchError,
    CollectionNotFoundError,
    PendingUpload,
    SourceFileNotFoundError,
    SourceNotFoundError,
    UnknownPrincipalError,
    UnsupportedSearchKindError,
    create_pending_batch,
    create_private_collection,
    delete_collection,
    delete_source,
    get_batch_progress,
    get_collection,
    get_source_preview,
    ingest_private_upload,
    list_collections,
    list_sources,
    resolve_source_file,
    search_chunks,
)

logger = structlog.stdlib.get_logger(__name__)

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

# What the download/preview endpoint serves each stored original as, plus how a client
# should render it. HTML is deliberately demoted to text/plain and download-only: it is
# user-supplied markup, and serving it inline from the API origin would let an uploaded
# file run script against that origin.
_TEXT_MEDIA_TYPE = "text/plain; charset=utf-8"
_SERVED_FILE_BY_SUFFIX: dict[str, tuple[str, SourcePreviewMode]] = {
    ".md": ("text/markdown; charset=utf-8", SourcePreviewMode.TEXT),
    ".markdown": ("text/markdown; charset=utf-8", SourcePreviewMode.TEXT),
    ".txt": (_TEXT_MEDIA_TYPE, SourcePreviewMode.TEXT),
    ".htm": (_TEXT_MEDIA_TYPE, SourcePreviewMode.DOWNLOAD),
    ".html": (_TEXT_MEDIA_TYPE, SourcePreviewMode.DOWNLOAD),
    ".pdf": ("application/pdf", SourcePreviewMode.PDF),
    ".docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        SourcePreviewMode.DOWNLOAD,
    ),
}

# Bounds for one preview payload. A 10 MB upload parses into far more text than a drawer
# should render at once, so the response carries a prefix and says that it did.
_PREVIEW_RAW_TEXT_LIMIT = 200_000
_PREVIEW_DEFAULT_CHUNK_LIMIT = 200
_PREVIEW_MAX_CHUNK_LIMIT = 1_000


def _assert_every_parsed_suffix_is_mapped() -> None:
    """Fail at import instead of rejecting a parsable upload with an empty expected set.

    ``ParserFactory`` is the single source of truth for what can be parsed.  Registering a
    parser without listing its content types would otherwise make that format permanently
    unuploadable — or uploadable but impossible to preview — so the mismatch is raised
    here rather than discovered by a user.
    """

    supported_suffixes = set(ParserFactory.supported_suffixes())
    for table_name, table in (
        ("_MIME_TYPES_BY_SUFFIX", _MIME_TYPES_BY_SUFFIX),
        ("_SERVED_FILE_BY_SUFFIX", _SERVED_FILE_BY_SUFFIX),
    ):
        unmapped = sorted(supported_suffixes - set(table))
        if unmapped:
            raise RuntimeError(
                f"Parsable suffixes missing from {table_name}: {', '.join(unmapped)}. "
                f"Add them to {table_name}."
            )


_assert_every_parsed_suffix_is_mapped()


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

    if not result.skipped:
        await _store_original_bytes(result.source_id, filename, file_bytes)

    return UploadResponse(
        source_id=result.source_id,
        document_id=result.document_id,
        chunk_count=result.chunk_count,
        skipped=result.skipped,
    )


async def _store_original_bytes(source_id: UUID, filename: str, file_bytes: bytes) -> None:
    """Keep the uploaded original so it can be previewed and downloaded later.

    Unlike the batch route, this runs after the ingest transaction has committed: the
    document is already parsed, chunked and searchable. A storage failure therefore must
    not turn a successful ingest into an error — it only costs the user the original-file
    preview, which the preview endpoint reports as ``original_available: false``.
    """

    try:
        await LocalUploadStorage().save(source_id, filename, file_bytes)
    except OSError as error:
        logger.warning(
            "upload.original_not_stored",
            source_id=str(source_id),
            filename=filename,
            error=str(error),
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


@router.get(
    "/collections",
    response_model=CollectionListResponse,
    summary="List knowledge-base collections visible to the current user",
)
async def list_kb_collections(
    current_user_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
    kind: Annotated[CollectionKind | None, Query()] = None,
) -> CollectionListResponse:
    """Return public collections plus the user's private ones, with live counts."""

    collections = await list_collections(session, current_user_id=current_user_id, kind=kind)
    return CollectionListResponse(
        collections=[
            CollectionSummary(
                id=collection.id,
                kind=collection.kind,
                scope=collection.scope,
                name=collection.name,
                source_count=collection.source_count,
                document_count=collection.document_count,
                chunk_count=collection.chunk_count,
            )
            for collection in collections
        ]
    )


@router.post(
    "/collections",
    response_model=CollectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a private knowledge-base collection owned by the current user",
)
async def create_kb_collection(
    payload: CreateCollectionRequest,
    current_user_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CollectionResponse:
    """Create a private collection of any of the four library kinds."""

    try:
        collection = await create_private_collection(
            session,
            current_user_id=current_user_id,
            kind=payload.kind,
            name=payload.name,
        )
    except CollectionAlreadyExistsError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except UnknownPrincipalError as error:
        # The identity in X-User-ID is well-formed but names nobody, so this is a
        # rejected principal (401), not a conflict the caller could rename away.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(error),
        ) from error

    await session.commit()
    return CollectionResponse(
        id=collection.id,
        kind=collection.kind,
        scope=collection.scope,
        name=collection.name,
        user_id=collection.user_id,
    )


@router.get(
    "/collections/{collection_id}",
    response_model=CollectionResponse,
    summary="Get one collection's metadata",
)
async def get_kb_collection(
    collection_id: UUID,
    current_user_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CollectionResponse:
    """Return one collection if it is public or owned by the current user."""

    collection = await get_collection(session, collection_id=collection_id)
    if collection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Collection {collection_id} was not found",
        )
    if collection.scope is not CollectionScope.PUBLIC and collection.user_id != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the owner may view this collection",
        )
    return CollectionResponse(
        id=collection.id,
        kind=collection.kind,
        scope=collection.scope,
        name=collection.name,
        user_id=collection.user_id,
    )


@router.get(
    "/collections/{collection_id}/sources",
    response_model=SourceListResponse,
    summary="List uploaded sources (documents) in a collection with ingest status",
)
async def list_kb_sources(
    collection_id: UUID,
    current_user_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SourceListResponse:
    """Return the documents in a visible collection, newest first."""

    try:
        sources = await list_sources(
            session, current_user_id=current_user_id, collection_id=collection_id
        )
    except CollectionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except CollectionAccessError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error

    return SourceListResponse(
        sources=[
            SourceSummary(
                source_id=source.source_id,
                filename=source.filename,
                ingest_status=source.ingest_status,
                dir_path=source.dir_path,
                created_at=source.created_at,
                document_id=source.document_id,
                title=source.title,
                chunk_count=source.chunk_count,
            )
            for source in sources
        ]
    )


@router.get(
    "/sources/{source_id}/preview",
    response_model=SourcePreviewResponse,
    summary="Get one source's file facts, parsed text and ordered chunks",
)
async def preview_kb_source(
    source_id: UUID,
    current_user_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
    chunk_limit: Annotated[
        int, Query(ge=1, le=_PREVIEW_MAX_CHUNK_LIMIT)
    ] = _PREVIEW_DEFAULT_CHUNK_LIMIT,
) -> SourcePreviewResponse:
    """Return everything the management UI renders for one uploaded document."""

    try:
        preview = await get_source_preview(
            session,
            current_user_id=current_user_id,
            source_id=source_id,
            raw_text_limit=_PREVIEW_RAW_TEXT_LIMIT,
            chunk_limit=chunk_limit,
        )
    except SourceNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except CollectionAccessError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error

    suffix = Path(preview.filename).suffix.casefold()
    media_type, preview_mode = _served_file_for(suffix)
    return SourcePreviewResponse(
        source_id=preview.source_id,
        filename=preview.filename,
        suffix=suffix,
        media_type=media_type,
        preview_mode=preview_mode,
        ingest_status=preview.ingest_status,
        dir_path=preview.dir_path,
        created_at=preview.created_at,
        error_message=preview.error_message,
        original_available=preview.stored_file is not None,
        size_bytes=None if preview.stored_file is None else preview.stored_file.size_bytes,
        document_id=preview.document_id,
        title=preview.title,
        raw_text=preview.raw_text,
        raw_text_truncated=preview.raw_text_truncated,
        chunk_count=preview.chunk_count,
        chunks=[
            SourceChunkPreview(
                chunk_id=chunk.chunk_id,
                ordinal=chunk.ordinal,
                text=chunk.text,
                token_count=chunk.token_count,
            )
            for chunk in preview.chunks
        ],
        chunks_truncated=preview.chunks_truncated,
    )


@router.get(
    "/sources/{source_id}/file",
    summary="Stream the original uploaded file for preview or download",
    response_class=FileResponse,
)
async def download_kb_source_file(
    source_id: UUID,
    current_user_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
    download: Annotated[bool, Query(description="Force an attachment disposition")] = False,
) -> FileResponse:
    """Serve the stored original bytes; 404 when only the parsed text survives."""

    try:
        source, stored_file = await resolve_source_file(
            session,
            current_user_id=current_user_id,
            source_id=source_id,
        )
    except SourceFileNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except SourceNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except CollectionAccessError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error

    # Source.filename may carry a relative seed path; only its final component names the
    # file on disk, and it is what the browser should use for a Save As.
    download_name = Path(source.filename).name
    media_type, preview_mode = _served_file_for(Path(download_name).suffix.casefold())
    disposition = (
        "attachment" if download or preview_mode is SourcePreviewMode.DOWNLOAD else "inline"
    )
    return FileResponse(
        stored_file.path,
        media_type=media_type,
        filename=download_name,
        content_disposition_type=disposition,
        # The served type is chosen from the suffix above, never sniffed from content;
        # nosniff stops a browser from overriding that and executing the file instead.
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=0"},
    )


def _served_file_for(suffix: str) -> tuple[str, SourcePreviewMode]:
    """Map a stored suffix to its served content type and client render mode.

    An unmapped suffix cannot reach the database through either upload route, but a
    hand-inserted or future record must still degrade to a plain download rather than
    raise a 500.
    """

    return _SERVED_FILE_BY_SUFFIX.get(suffix, (_UNKNOWN_MIME_TYPE, SourcePreviewMode.DOWNLOAD))


@router.delete(
    "/sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete an uploaded source and remove its chunks",
)
async def delete_kb_source(
    source_id: UUID,
    current_user_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    """Delete one uploaded document from a private collection the user owns."""

    try:
        await delete_source(session, current_user_id=current_user_id, source_id=source_id)
    except SourceNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except CollectionAccessError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error


@router.delete(
    "/collections/{collection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a private collection and all its data",
)
async def delete_kb_collection(
    collection_id: UUID,
    current_user_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    """Hard-delete a private collection owned by the current user."""

    try:
        await delete_collection(
            session, current_user_id=current_user_id, collection_id=collection_id
        )
    except CollectionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except CollectionAccessError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
