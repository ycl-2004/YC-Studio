"""Collection-aware orchestration for the ingestion pipeline.

Aligns with Stage 1 Step 5 (chunking policy) and Step 7 (ingest, dedup, bulk insert).
"""

import hashlib
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.chunk import Chunk
from app.db.models.collection import Collection, CollectionKind
from app.db.models.document import Document
from app.db.models.source import IngestStatus, Source
from app.rag.chunker import Chunk as ChunkData
from app.rag.chunker import TextChunker
from app.rag.cleaner import TextCleaner
from app.rag.parsers.base import ParseResult
from app.rag.parsers.factory import parse_file
from app.rag.retriever.embeddings import encode_texts, get_local_embedding

logger = structlog.stdlib.get_logger(__name__)

_WHOLE_DOCUMENT_KINDS = frozenset({CollectionKind.RULE, CollectionKind.TEMPLATE})

# error_message is Text, but a stack-trace-sized string in a status column helps nobody.
_MAX_ERROR_MESSAGE_LENGTH = 500


@dataclass(frozen=True, slots=True)
class IngestResult:
    """Outcome of a single file ingestion attempt."""

    source_id: UUID
    document_id: UUID | None
    chunk_count: int
    skipped: bool
    error: str | None = None


def compute_content_hash(data: bytes) -> str:
    """Compute SHA-256 hex digest of raw file bytes."""
    return hashlib.sha256(data).hexdigest()


def _is_whole_document_kind(kind: CollectionKind) -> bool:
    """Whether this library is consumed whole rather than retrieved by similarity.

    One predicate drives both halves of the policy: rule and template libraries skip
    chunking *and* skip embedding, because they are injected in full by SQL. Splitting
    the two decisions is how a rulebook ends up with a vector for its first 512 tokens.
    """

    return kind in _WHOLE_DOCUMENT_KINDS


def chunk_for_collection(
    text: str,
    kind: CollectionKind,
    chunker: TextChunker,
) -> list[ChunkData]:
    """Apply four-layer knowledge-base chunking policy to cleaned document text."""

    if _is_whole_document_kind(kind):
        return chunker.preserve_as_single_chunk(text)
    return chunker.split(text)


def _fit_chunk_budget(
    max_tokens: int,
    overlap_tokens: int,
    model_limit: int | None,
) -> tuple[int, int]:
    """Cap the configured chunk budget at what the encoder can actually read.

    A chunk longer than the model's window is not an error anyone sees: the encoder
    truncates it and returns a vector for the surviving prefix, so the tail of the
    chunk becomes unsearchable while the row still looks healthy. Deriving the ceiling
    from the model keeps that impossible for any configured value or any model swap.

    Returns:
        The chunk and overlap token budgets to hand the chunker. The overlap is scaled
        down proportionally so its share of a chunk stays what was configured.
    """

    if model_limit is None or max_tokens <= model_limit:
        return max_tokens, overlap_tokens

    overlap_ratio = overlap_tokens / max_tokens
    fitted_overlap = min(int(model_limit * overlap_ratio), model_limit - 1)
    logger.warning(
        "Configured chunk size exceeds the embedding model's window; capping it",
        configured_chunk_size=max_tokens,
        model_max_input_tokens=model_limit,
        effective_chunk_size=model_limit,
        effective_overlap=fitted_overlap,
    )
    return model_limit, fitted_overlap


def _parse_upload(
    filename: str,
    file_bytes: bytes,
    file_path: Path | None,
) -> ParseResult:
    """Parse an upload from disk, since every parser reads a Path.

    Parsers derive the document title from the file stem, so bytes are staged under
    the original filename inside a temporary directory rather than under the random
    name ``NamedTemporaryFile`` would produce.
    """

    if file_path is not None:
        return parse_file(file_path)

    with tempfile.TemporaryDirectory(prefix="ycstudio-ingest-") as staging_dir:
        staged_path = Path(staging_dir) / Path(filename).name
        staged_path.write_bytes(file_bytes)
        return parse_file(staged_path)


async def ingest_document(
    session: AsyncSession,
    collection_id: UUID,
    filename: str,
    file_bytes: bytes,
    *,
    file_path: Path | None = None,
    dir_path: str | None = None,
    metadata: dict[str, str] | None = None,
    count_tokens: Callable[[str], int] | None = None,
) -> IngestResult:
    """Full ingestion pipeline: hash → dedup → parse → clean → chunk → embed → bulk insert.

    The caller owns the transaction boundary and must commit. On failure the pipeline
    rolls back to a savepoint taken right after the source row is inserted, so the
    ``failed`` status and its error message survive the caller's commit while the
    half-written document and chunks do not.

    Args:
        session: Active async database session (caller owns transaction boundary).
        collection_id: Target knowledge base collection UUID.
        filename: Original filename (used for parser dispatch and metadata).
        file_bytes: Raw file content bytes.
        file_path: Optional on-disk path to parse instead of staging ``file_bytes``.
        dir_path: Optional directory path metadata for folder uploads.
        metadata: User-confirmed document metadata from the upload form.
        count_tokens: Token counter for the chunker. Defaults to the embedding model's
            own tokenizer so chunk boundaries are measured in the units the encoder
            actually consumes.

    Returns:
        IngestResult with source_id, document_id, chunk_count, and skipped flag.

    Raises:
        ValueError: The target collection does not exist.
        Exception: Any parser, embedding, or database failure, after the source row
            has been marked ``failed``.
    """
    settings = get_settings()
    content_hash = compute_content_hash(file_bytes)

    # ── Dedup: same bytes in the same collection short-circuit before any work ──
    existing_source = await _find_existing_source(session, collection_id, content_hash)
    if existing_source is not None:
        logger.info(
            "Duplicate file detected, short-circuiting",
            filename=filename,
            content_hash=content_hash,
            existing_source_id=str(existing_source.id),
        )
        return IngestResult(
            source_id=existing_source.id,
            document_id=None,
            chunk_count=0,
            skipped=True,
        )

    collection = await session.get(Collection, collection_id)
    if collection is None:
        raise ValueError(f"Collection {collection_id} not found")

    source = Source(
        collection_id=collection_id,
        filename=filename,
        content_hash=content_hash,
        dir_path=dir_path,
        ingest_status=IngestStatus.PENDING,
    )
    session.add(source)
    await session.flush()
    source_id = source.id
    logger.info("Source record created", source_id=str(source_id), filename=filename)

    savepoint = await session.begin_nested()
    try:
        result = await _run_pipeline(
            session,
            source=source,
            collection=collection,
            filename=filename,
            file_bytes=file_bytes,
            file_path=file_path,
            metadata=metadata,
            count_tokens=count_tokens,
            embedding_batch_size=settings.embedding_batch_size,
            insert_batch_size=settings.ingest_batch_size,
            max_tokens=settings.chunk_size,
            overlap_tokens=settings.chunk_overlap,
        )
    except Exception as exc:
        if savepoint.is_active:
            await savepoint.rollback()
        # Attribute assignment would need a refresh of an expired instance; a direct
        # UPDATE keeps the failure record write free of extra async round trips.
        await session.execute(
            update(Source)
            .where(Source.id == source_id)
            .values(
                ingest_status=IngestStatus.FAILED,
                error_message=str(exc)[:_MAX_ERROR_MESSAGE_LENGTH],
            )
        )
        await session.flush()
        logger.error(
            "Ingestion failed",
            source_id=str(source_id),
            filename=filename,
            error=str(exc),
        )
        raise

    await savepoint.commit()
    return result


async def ingest_pending_source(
    session: AsyncSession,
    *,
    source: Source,
    collection: Collection,
    file_bytes: bytes,
    metadata: dict[str, str],
) -> IngestResult:
    """Process a durable pending source created before an ARQ job was enqueued.

    A cancelled worker leaves its transaction uncommitted, so ARQ can safely run the
    same pending source again without creating a second Source row.
    """

    source_id = source.id
    if source.ingest_status is IngestStatus.COMPLETED:
        return IngestResult(source_id, None, 0, skipped=True)
    if source.ingest_status is not IngestStatus.PENDING:
        return IngestResult(source_id, None, 0, skipped=True)

    settings = get_settings()
    savepoint = await session.begin_nested()
    try:
        result = await _run_pipeline(
            session,
            source=source,
            collection=collection,
            filename=source.filename,
            file_bytes=file_bytes,
            file_path=None,
            metadata=metadata,
            count_tokens=None,
            embedding_batch_size=settings.embedding_batch_size,
            insert_batch_size=settings.ingest_batch_size,
            max_tokens=settings.chunk_size,
            overlap_tokens=settings.chunk_overlap,
        )
    except Exception as exc:
        if savepoint.is_active:
            await savepoint.rollback()
        # source_id was captured before the savepoint opened; source.id would trigger a
        # synchronous lazy-load on the now-expired instance and raise MissingGreenlet
        # instead of recording this exception (see app/tasks/ingest_tasks.py).
        await session.execute(
            update(Source)
            .where(Source.id == source_id)
            .values(
                ingest_status=IngestStatus.FAILED,
                error_message=str(exc)[:_MAX_ERROR_MESSAGE_LENGTH],
            )
        )
        await session.flush()
        raise

    await savepoint.commit()
    return result


async def _run_pipeline(
    session: AsyncSession,
    *,
    source: Source,
    collection: Collection,
    filename: str,
    file_bytes: bytes,
    file_path: Path | None,
    metadata: dict[str, str] | None,
    count_tokens: Callable[[str], int] | None,
    embedding_batch_size: int,
    insert_batch_size: int,
    max_tokens: int,
    overlap_tokens: int,
) -> IngestResult:
    """Run parse → clean → chunk → embed → insert inside the caller's savepoint."""

    source.ingest_status = IngestStatus.PARSING
    await session.flush()
    parse_result = _parse_upload(filename, file_bytes, file_path)

    cleaned_text = TextCleaner().clean(parse_result.text)

    document = Document(
        source_id=source.id,
        title=parse_result.title,
        raw_text=cleaned_text,
        # source.dir_path only exists for folder uploads (Step 9); it belongs in filterable
        # metadata, not just on Source, or "filter search by folder" has no way to work.
        meta={
            **parse_result.meta,
            **(metadata or {}),
            **({"dir_path": source.dir_path} if source.dir_path else {}),
        },
        parser_version=parse_result.parser_version,
    )
    session.add(document)
    await session.flush()

    source.ingest_status = IngestStatus.CHUNKING
    await session.flush()

    if _is_whole_document_kind(collection.kind):
        # Whole-document libraries are never embedded, so loading the embedding model merely
        # to count a non-searchable row makes the public seed command depend on an ML cache.
        # The stored count is informational; a caller may still supply an exact counter.
        chunker = TextChunker(
            count_tokens if count_tokens is not None else len,
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens,
        )
        embedding = None
    else:
        embedding = get_local_embedding()
        effective_max_tokens, effective_overlap = _fit_chunk_budget(
            max_tokens,
            overlap_tokens,
            embedding.max_input_tokens,
        )
        chunker = TextChunker(
            count_tokens if count_tokens is not None else embedding.count_tokens,
            max_tokens=effective_max_tokens,
            overlap_tokens=effective_overlap,
        )
    chunk_data_list = chunk_for_collection(cleaned_text, collection.kind, chunker)

    if not chunk_data_list:
        source.ingest_status = IngestStatus.COMPLETED
        await session.flush()
        logger.warning(
            "Document produced no chunks",
            source_id=str(source.id),
            document_id=str(document.id),
            filename=filename,
        )
        return IngestResult(
            source_id=source.id,
            document_id=document.id,
            chunk_count=0,
            skipped=False,
        )

    if _is_whole_document_kind(collection.kind):
        # Rule and template libraries are injected whole and never ranked by similarity,
        # so their vector would only ever be the truncated head of a long document.
        vectors: list[list[float] | None] = [None] * len(chunk_data_list)
        embed_model: str | None = None
        embed_version: str | None = None
        logger.info(
            "Skipping embedding for a whole-document collection",
            collection_kind=collection.kind.value,
            document_id=str(document.id),
            chunk_count=len(chunk_data_list),
        )
    else:
        source.ingest_status = IngestStatus.EMBEDDING
        await session.flush()
        vectors = list(
            encode_texts(
                [chunk.text for chunk in chunk_data_list],
                batch_size=embedding_batch_size,
            )
        )
        if embedding is None:  # pragma: no cover - guarded by the collection-kind branch above.
            raise RuntimeError("Searchable collections require an embedding model")
        embed_model = embedding.embed_model
        embed_version = embedding.embed_version

    chunk_rows = [
        Chunk(
            collection_id=collection.id,
            document_id=document.id,
            ordinal=chunk_data.ordinal,
            text=chunk_data.text,
            token_count=chunk_data.token_count,
            embedding=vector,
            embed_model=embed_model,
            embed_version=embed_version,
        )
        # strict=True turns a truncated encoder response into a loud failure rather
        # than a document that silently loses its tail chunks.
        for chunk_data, vector in zip(chunk_data_list, vectors, strict=True)
    ]

    await _bulk_insert_chunks(session, chunk_rows, batch_size=insert_batch_size)

    source.ingest_status = IngestStatus.COMPLETED
    await session.flush()

    logger.info(
        "Ingestion completed",
        source_id=str(source.id),
        document_id=str(document.id),
        chunk_count=len(chunk_rows),
        embed_model=embed_model,
        embed_version=embed_version,
    )

    return IngestResult(
        source_id=source.id,
        document_id=document.id,
        chunk_count=len(chunk_rows),
        skipped=False,
    )


async def _find_existing_source(
    session: AsyncSession,
    collection_id: UUID,
    content_hash: str,
) -> Source | None:
    """Check if a source with matching (collection_id, content_hash) already exists."""
    stmt = select(Source).where(
        Source.collection_id == collection_id,
        Source.content_hash == content_hash,
        Source.deleted_at.is_(None),
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _bulk_insert_chunks(
    session: AsyncSession,
    chunks: list[Chunk],
    batch_size: int = 200,
) -> None:
    """Insert chunks in batches to stay under PostgreSQL's parameter limit.

    A single statement may bind at most 32767 parameters. A chunk row binds nine, so
    200 rows per batch leaves a wide margin while keeping the number of round trips
    low for a document that produces thousands of chunks.
    """
    for offset in range(0, len(chunks), batch_size):
        batch = chunks[offset : offset + batch_size]
        session.add_all(batch)
        await session.flush()
        logger.debug(
            "Chunk batch inserted",
            batch_start=offset,
            batch_size=len(batch),
            total=len(chunks),
        )
