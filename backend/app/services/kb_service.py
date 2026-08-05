"""Knowledge-base use cases kept independent from FastAPI request objects.

Vector distance uses pgvector's cosine-distance operator.  Stored embeddings and
query vectors are normalized, so ``1 - distance / 2`` maps cosine similarity from
[-1, 1] to the API's documented [0, 1] score range.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
from uuid import UUID

from sqlalchemy import ColumnElement, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.adapters.storage import LocalUploadStorage, StoredFile
from app.db.models.chunk import Chunk
from app.db.models.collection import Collection, CollectionKind, CollectionScope
from app.db.models.document import Document
from app.db.models.ingest_batch import IngestBatch
from app.db.models.source import IngestStatus, Source
from app.rag.retriever.embeddings import get_local_embedding
from app.schemas.kb import SearchRequest
from app.services.ingest_service import (
    IngestResult,
    compute_content_hash,
    find_existing_source,
    ingest_document,
    is_reingestable,
    reset_source_for_reingest,
)

_SEARCHABLE_KINDS = frozenset({CollectionKind.CASE, CollectionKind.MATERIAL})

# PostgreSQL integrity SQLSTATEs. Class 23 codes are stable across versions and
# locales, unlike the constraint names and messages in the exception text.
# https://www.postgresql.org/docs/current/errcodes-appendix.html
_UNIQUE_VIOLATION = "23505"
_FOREIGN_KEY_VIOLATION = "23503"


class CollectionNotFoundError(LookupError):
    """The requested collection does not exist."""


class CollectionAccessError(PermissionError):
    """The request principal cannot write to the selected collection."""


class CollectionKindMismatchError(ValueError):
    """The upload form kind does not describe the selected collection."""


class UnsupportedSearchKindError(ValueError):
    """The requested collection kind is deliberately not vector-searchable."""


@dataclass(frozen=True, slots=True)
class PendingUpload:
    """Validated bytes and optional client-supplied directory metadata for one file."""

    filename: str
    file_bytes: bytes
    dir_path: str | None


@dataclass(frozen=True, slots=True)
class BatchProgress:
    """Counts used to expose batch state without consulting ephemeral ARQ results."""

    batch_id: UUID
    total: int
    completed: int
    failed: int
    in_progress: int
    pending: int


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    """A retrieval row plus the provenance required by the client."""

    chunk: Chunk
    document: Document
    source: Source
    score: float


async def ingest_private_upload(
    session: AsyncSession,
    *,
    current_user_id: UUID,
    collection_id: UUID,
    kind: CollectionKind,
    filename: str,
    file_bytes: bytes,
    metadata: dict[str, str],
) -> IngestResult:
    """Authorize and synchronously ingest one file into an owned private collection."""

    collection = await session.get(Collection, collection_id)
    if collection is None:
        raise CollectionNotFoundError(f"Collection {collection_id} was not found")
    if collection.scope is not CollectionScope.PRIVATE or collection.user_id != current_user_id:
        raise CollectionAccessError("Only the owner may upload to a private collection")
    if collection.kind is not kind:
        raise CollectionKindMismatchError(
            f"Form kind {kind.value!r} does not match collection kind {collection.kind.value!r}"
        )

    try:
        result = await ingest_document(
            session,
            collection_id=collection_id,
            filename=filename,
            file_bytes=file_bytes,
            metadata=metadata,
        )
    except Exception:
        # ingest_document records a failed Source outside its internal savepoint.
        # Commit that record before returning the client an error.
        await session.commit()
        raise

    await session.commit()
    return result


async def create_pending_batch(
    session: AsyncSession,
    *,
    current_user_id: UUID,
    collection_id: UUID,
    kind: CollectionKind,
    metadata: dict[str, str],
    uploads: list[PendingUpload],
) -> tuple[IngestBatch, list[Source]]:
    """Persist a batch and pending Sources before any file is placed on the queue."""

    collection = await _owned_private_collection(
        session,
        current_user_id=current_user_id,
        collection_id=collection_id,
        kind=kind,
    )
    batch = IngestBatch(
        collection_id=collection.id,
        user_id=current_user_id,
        upload_metadata=metadata,
    )
    session.add(batch)
    await session.flush()

    sources: list[Source] = []
    seen_hashes: set[str] = set()
    for upload in uploads:
        content_hash = compute_content_hash(upload.file_bytes)
        if content_hash in seen_hashes:
            raise ValueError("A batch cannot include the same file content twice.")
        seen_hashes.add(content_hash)
        dir_path = _normalise_dir_path(upload.dir_path)
        # Same rule as the synchronous route: a failed or deleted row is a retry, and
        # it must be reused because the unique index also covers deleted rows.
        existing = await find_existing_source(session, collection.id, content_hash)
        if existing is not None and not is_reingestable(existing):
            raise ValueError("This collection already contains one of the uploaded files.")
        if existing is None:
            source = Source(
                collection_id=collection.id,
                batch_id=batch.id,
                filename=upload.filename,
                content_hash=content_hash,
                dir_path=dir_path,
                ingest_status=IngestStatus.PENDING,
            )
            session.add(source)
        else:
            source = await reset_source_for_reingest(
                session,
                existing,
                filename=upload.filename,
                dir_path=dir_path,
            )
            source.batch_id = batch.id
        sources.append(source)
    await session.flush()
    return batch, sources


async def get_batch_progress(
    session: AsyncSession,
    *,
    current_user_id: UUID,
    batch_id: UUID,
) -> BatchProgress:
    """Return database counters for a batch owned by the current principal."""

    batch = await session.get(IngestBatch, batch_id)
    if batch is None:
        raise CollectionNotFoundError(f"Batch {batch_id} was not found")
    if batch.user_id != current_user_id:
        raise CollectionAccessError("Only the owner may view this batch")

    rows = await session.execute(
        select(Source.ingest_status, func.count())
        .where(Source.batch_id == batch_id)
        .group_by(Source.ingest_status)
    )
    counts = {status: int(count) for status, count in rows}
    completed = counts.get(IngestStatus.COMPLETED, 0)
    failed = counts.get(IngestStatus.FAILED, 0)
    pending = counts.get(IngestStatus.PENDING, 0)
    in_progress = sum(
        counts.get(status, 0)
        for status in (IngestStatus.PARSING, IngestStatus.CHUNKING, IngestStatus.EMBEDDING)
    )
    return BatchProgress(
        batch_id=batch_id,
        total=sum(counts.values()),
        completed=completed,
        failed=failed,
        in_progress=in_progress,
        pending=pending,
    )


async def _owned_private_collection(
    session: AsyncSession,
    *,
    current_user_id: UUID,
    collection_id: UUID,
    kind: CollectionKind,
) -> Collection:
    """Load the exact private collection that an upload may use."""

    collection = await session.get(Collection, collection_id)
    if collection is None:
        raise CollectionNotFoundError(f"Collection {collection_id} was not found")
    if collection.scope is not CollectionScope.PRIVATE or collection.user_id != current_user_id:
        raise CollectionAccessError("Only the owner may upload to a private collection")
    if collection.kind is not kind:
        raise CollectionKindMismatchError(
            f"Form kind {kind.value!r} does not match collection kind {collection.kind.value!r}"
        )
    return collection


def _normalise_dir_path(dir_path: str | None) -> str | None:
    """Accept a relative POSIX client path only; never let it become a filesystem path."""

    if dir_path is None or not dir_path.strip():
        return None
    normalised = dir_path.replace("\\", "/").strip("/")
    path = PurePosixPath(normalised)
    if path.is_absolute() or ".." in path.parts or normalised in {"", "."}:
        raise ValueError("dir_path must be a non-empty relative path without '..'.")
    if len(normalised) > 200:
        raise ValueError("dir_path must be at most 200 characters.")
    return normalised


async def search_chunks(
    session: AsyncSession,
    *,
    current_user_id: UUID,
    request: SearchRequest,
) -> list[RetrievedChunk]:
    """Find searchable chunks visible to the principal, ordered by cosine relevance."""

    if request.kind not in _SEARCHABLE_KINDS:
        raise UnsupportedSearchKindError(
            f"The {request.kind.value!r} library is not searchable; "
            "use its deterministic access path."
        )

    query_vector = get_local_embedding().embed_query(request.query)
    distance = Chunk.embedding.cosine_distance(query_vector).label("cosine_distance")
    statement = (
        select(Chunk, Document, Source, distance)
        .join(Document, Chunk.document_id == Document.id)
        .join(Source, Document.source_id == Source.id)
        .join(Collection, Chunk.collection_id == Collection.id)
        .where(
            Chunk.embedding.is_not(None),
            Collection.kind == request.kind,
            Document.deleted_at.is_(None),
            Source.deleted_at.is_(None),
            or_(
                Collection.scope == CollectionScope.PUBLIC,
                Collection.user_id == current_user_id,
            ),
        )
        .order_by(distance)
        .limit(request.top_k)
    )
    if request.metadata_filter:
        statement = statement.where(Document.meta.contains(request.metadata_filter))

    rows = (await session.execute(statement)).all()
    return [
        RetrievedChunk(
            chunk=chunk,
            document=document,
            source=source,
            score=_cosine_distance_to_score(float(raw_distance)),
        )
        for chunk, document, source, raw_distance in rows
    ]


def _cosine_distance_to_score(distance: float) -> float:
    """Convert cosine distance in [0, 2] into monotonic API similarity in [0, 1]."""

    return min(1.0, max(0.0, 1.0 - distance / 2.0))


class CollectionAlreadyExistsError(ValueError):
    """A private collection with the same (owner, kind, name) already exists."""


class UnknownPrincipalError(LookupError):
    """The request principal has no user row, so it cannot own anything.

    Until Stage 4 replaces ``X-User-ID`` with verified identity, a caller can send a
    well-formed UUID that names nobody. Owning data is the one operation that cannot
    quietly tolerate that, so it is reported instead of failing as a database error.
    """


class SourceNotFoundError(LookupError):
    """The requested source does not exist."""


class SourceFileNotFoundError(LookupError):
    """The source is visible but its original uploaded bytes were never stored.

    Distinct from ``SourceNotFoundError``: the document and its parsed text are
    perfectly usable, only the byte-for-byte original is unavailable.
    """


@dataclass(frozen=True, slots=True)
class CollectionView:
    """A collection plus the live counts the management UI needs to render tabs."""

    id: UUID
    kind: CollectionKind
    scope: CollectionScope
    name: str
    source_count: int
    document_count: int
    chunk_count: int


@dataclass(frozen=True, slots=True)
class SourceView:
    """An uploaded source (document) with its derived document and chunk counts."""

    source_id: UUID
    filename: str
    ingest_status: IngestStatus
    dir_path: str | None
    created_at: datetime
    document_id: UUID | None
    title: str | None
    chunk_count: int


@dataclass(frozen=True, slots=True)
class ChunkPreview:
    """One stored chunk in document order, without its embedding vector."""

    chunk_id: UUID
    ordinal: int
    text: str
    token_count: int


@dataclass(frozen=True, slots=True)
class SourcePreview:
    """One uploaded file as the management UI shows it: facts, parsed text, chunks.

    ``stored_file`` is ``None`` when only the parsed text survives; see
    ``LocalUploadStorage.find``.
    """

    source_id: UUID
    filename: str
    ingest_status: IngestStatus
    dir_path: str | None
    created_at: datetime
    error_message: str | None
    stored_file: StoredFile | None
    document_id: UUID | None
    title: str | None
    raw_text: str | None
    raw_text_truncated: bool
    chunk_count: int
    chunks: list[ChunkPreview]
    chunks_truncated: bool


async def list_collections(
    session: AsyncSession,
    *,
    current_user_id: UUID,
    kind: CollectionKind | None = None,
) -> list[CollectionView]:
    """Return public collections and the user's private ones, with live counts."""

    statement = (
        select(Collection)
        .where(
            or_(
                Collection.scope == CollectionScope.PUBLIC,
                Collection.user_id == current_user_id,
            )
        )
        .order_by(Collection.kind, Collection.name)
    )
    if kind is not None:
        statement = statement.where(Collection.kind == kind)
    collections = (await session.execute(statement)).scalars().all()
    if not collections:
        return []

    ids = [collection.id for collection in collections]
    source_counts = await _count_by_collection_column(
        session, Source.collection_id, Source.deleted_at.is_(None), ids
    )
    document_counts = await _count_documents_by_collection(session, ids)
    chunk_counts = await _count_chunks_by_collection(session, ids)

    return [
        CollectionView(
            collection.id,
            collection.kind,
            collection.scope,
            collection.name,
            source_counts.get(collection.id, 0),
            document_counts.get(collection.id, 0),
            chunk_counts.get(collection.id, 0),
        )
        for collection in collections
    ]


async def create_private_collection(
    session: AsyncSession,
    *,
    current_user_id: UUID,
    kind: CollectionKind,
    name: str,
) -> Collection:
    """Create a private collection owned by the current user.

    Two different constraints can reject this insert, and they mean opposite things
    to the caller, so the SQLSTATE decides which error is raised:

    - ``uq_kb_collections_owner_kind_name`` (23505) means the user already has this
      library — a conflict they can resolve by picking another name.
    - ``kb_collections_user_id_fkey`` (23503) means the principal itself has no user
      row, so nothing the caller renames will ever succeed.

    Reporting the second as "already exists" is what made an unknown principal look
    like a duplicate name; any other integrity failure is a real bug and propagates.
    """

    collection = Collection(
        user_id=current_user_id,
        kind=kind,
        scope=CollectionScope.PRIVATE,
        name=name,
    )
    session.add(collection)
    try:
        await session.flush()
    except IntegrityError as error:
        await session.rollback()
        domain_error = _classify_collection_integrity_error(
            error,
            current_user_id=current_user_id,
            kind=kind,
            name=name,
        )
        if domain_error is None:
            raise
        raise domain_error from error
    return collection


def _classify_collection_integrity_error(
    error: IntegrityError,
    *,
    current_user_id: UUID,
    kind: CollectionKind,
    name: str,
) -> Exception | None:
    """Turn a PostgreSQL integrity failure into the domain error it actually describes.

    ``error.orig`` is SQLAlchemy's asyncpg adapter exception, which copies the
    driver's five-character SQLSTATE onto ``sqlstate``. Matching on that rather than
    on the message text keeps this independent of constraint names and locales.
    """

    sqlstate = getattr(error.orig, "sqlstate", None)
    if sqlstate == _FOREIGN_KEY_VIOLATION:
        return UnknownPrincipalError(
            f"User {current_user_id} does not exist and cannot own a collection"
        )
    if sqlstate == _UNIQUE_VIOLATION:
        return CollectionAlreadyExistsError(
            f"A private {kind.value} collection named {name!r} already exists"
        )
    return None


async def get_collection(
    session: AsyncSession,
    *,
    collection_id: UUID,
) -> Collection | None:
    """Return the collection row or ``None`` if it does not exist."""

    return await session.get(Collection, collection_id)


async def list_sources(
    session: AsyncSession,
    *,
    current_user_id: UUID,
    collection_id: UUID,
) -> list[SourceView]:
    """List uploaded sources in a visible collection with document and chunk counts."""

    collection = await session.get(Collection, collection_id)
    if collection is None:
        raise CollectionNotFoundError(f"Collection {collection_id} was not found")
    if collection.scope is not CollectionScope.PUBLIC and collection.user_id != current_user_id:
        raise CollectionAccessError("Only the owner may view this collection")

    sources = (
        (
            await session.execute(
                select(Source)
                .where(Source.collection_id == collection_id, Source.deleted_at.is_(None))
                .order_by(Source.created_at.desc())
            )
        )
        .scalars()
        .all()
    )

    source_ids = [source.id for source in sources]
    documents = (
        (await session.execute(select(Document).where(Document.source_id.in_(source_ids))))
        .scalars()
        .all()
        if source_ids
        else []
    )
    document_by_source = {document.source_id: document for document in documents}

    chunk_counts: dict[UUID, int] = {}
    document_ids = [document.id for document in documents]
    if document_ids:
        rows = await session.execute(
            select(Chunk.document_id, func.count())
            .where(Chunk.document_id.in_(document_ids))
            .group_by(Chunk.document_id)
        )
        chunk_counts = {document_id: int(count) for document_id, count in rows}

    return [
        SourceView(
            source.id,
            source.filename,
            source.ingest_status,
            source.dir_path,
            source.created_at,
            document_by_source[source.id].id if source.id in document_by_source else None,
            document_by_source[source.id].title if source.id in document_by_source else None,
            chunk_counts.get(document_by_source[source.id].id, 0)
            if source.id in document_by_source
            else 0,
        )
        for source in sources
    ]


async def get_source_preview(
    session: AsyncSession,
    *,
    current_user_id: UUID,
    source_id: UUID,
    raw_text_limit: int,
    chunk_limit: int,
) -> SourcePreview:
    """Assemble file facts, parsed text and ordered chunks for one visible source.

    Both text payloads are bounded: a 10 MB upload parses into text no browser should
    be asked to render at once, so the caller receives a prefix plus a truncation flag
    rather than the whole document.
    """

    source = await _visible_source(session, current_user_id=current_user_id, source_id=source_id)
    stored_file = await LocalUploadStorage().find(source.id, source.filename)

    document = await session.scalar(
        select(Document)
        .where(Document.source_id == source.id, Document.deleted_at.is_(None))
        .order_by(Document.created_at.desc())
        .limit(1)
    )
    if document is None:
        return SourcePreview(
            source_id=source.id,
            filename=source.filename,
            ingest_status=source.ingest_status,
            dir_path=source.dir_path,
            created_at=source.created_at,
            error_message=source.error_message,
            stored_file=stored_file,
            document_id=None,
            title=None,
            raw_text=None,
            raw_text_truncated=False,
            chunk_count=0,
            chunks=[],
            chunks_truncated=False,
        )

    chunk_count = int(
        await session.scalar(
            select(func.count()).select_from(Chunk).where(Chunk.document_id == document.id)
        )
        or 0
    )
    # Selecting columns rather than the ORM entity keeps the 768-float embedding — which
    # no preview ever renders — off the wire for every chunk shown.
    chunk_rows = await session.execute(
        select(Chunk.id, Chunk.ordinal, Chunk.text, Chunk.token_count)
        .where(Chunk.document_id == document.id)
        .order_by(Chunk.ordinal)
        .limit(chunk_limit)
    )
    chunks = [
        ChunkPreview(chunk_id=chunk_id, ordinal=ordinal, text=text, token_count=token_count)
        for chunk_id, ordinal, text, token_count in chunk_rows
    ]

    return SourcePreview(
        source_id=source.id,
        filename=source.filename,
        ingest_status=source.ingest_status,
        dir_path=source.dir_path,
        created_at=source.created_at,
        error_message=source.error_message,
        stored_file=stored_file,
        document_id=document.id,
        title=document.title,
        raw_text=document.raw_text[:raw_text_limit],
        raw_text_truncated=len(document.raw_text) > raw_text_limit,
        chunk_count=chunk_count,
        chunks=chunks,
        chunks_truncated=chunk_count > len(chunks),
    )


async def resolve_source_file(
    session: AsyncSession,
    *,
    current_user_id: UUID,
    source_id: UUID,
) -> tuple[Source, StoredFile]:
    """Return the visible source and its on-disk original, for streaming or download."""

    source = await _visible_source(session, current_user_id=current_user_id, source_id=source_id)
    stored_file = await LocalUploadStorage().find(source.id, source.filename)
    if stored_file is None:
        raise SourceFileNotFoundError(
            f"The original file for source {source_id} is not stored; "
            "only its parsed text is available."
        )
    return source, stored_file


async def _visible_source(
    session: AsyncSession,
    *,
    current_user_id: UUID,
    source_id: UUID,
) -> Source:
    """Load one source the principal may read, applying the same rule as list_sources.

    Reading is wider than writing: a public collection is readable by everyone, while
    ``delete_source`` deliberately refuses public collections entirely.
    """

    source = await session.get(Source, source_id)
    if source is None or source.deleted_at is not None:
        raise SourceNotFoundError(f"Source {source_id} was not found")

    collection = await session.get(Collection, source.collection_id)
    if collection is None:
        raise SourceNotFoundError(f"Source {source_id} was not found")
    if collection.scope is not CollectionScope.PUBLIC and collection.user_id != current_user_id:
        raise CollectionAccessError("Only the owner may view this document")
    return source


async def delete_source(
    session: AsyncSession,
    *,
    current_user_id: UUID,
    source_id: UUID,
) -> None:
    """Soft-delete one uploaded source and remove its chunks from retrieval.

    The source and its documents are soft-deleted (kept for audit); their chunks are
    hard-deleted because generated content still references the documents, but chunks
    only ever live inside an un-deleted document. After this, the chunks are gone and
    the soft-deleted documents are excluded by the search filter either way.
    """

    source = await session.get(Source, source_id)
    if source is None:
        raise SourceNotFoundError(f"Source {source_id} was not found")

    collection = await session.get(Collection, source.collection_id)
    if (
        collection is None
        or collection.scope is CollectionScope.PUBLIC
        or collection.user_id != current_user_id
    ):
        raise CollectionAccessError("Only the owner may delete from a private collection")

    documents = (
        (await session.execute(select(Document).where(Document.source_id == source_id)))
        .scalars()
        .all()
    )
    document_ids = [document.id for document in documents]
    if document_ids:
        await session.execute(delete(Chunk).where(Chunk.document_id.in_(document_ids)))

    now = datetime.now(UTC)
    for document in documents:
        document.deleted_at = now
    source.deleted_at = now
    await session.commit()


async def delete_collection(
    session: AsyncSession,
    *,
    current_user_id: UUID,
    collection_id: UUID,
) -> None:
    """Hard-delete a private collection; cascade removes sources, documents and chunks."""

    collection = await session.get(Collection, collection_id)
    if collection is None:
        raise CollectionNotFoundError(f"Collection {collection_id} was not found")
    if collection.scope is not CollectionScope.PRIVATE or collection.user_id != current_user_id:
        raise CollectionAccessError("Only the owner may delete a private collection")

    await session.execute(delete(Collection).where(Collection.id == collection_id))
    await session.commit()


async def _count_by_collection_column(
    session: AsyncSession,
    column: InstrumentedAttribute[UUID],
    extra_filter: ColumnElement[bool],
    collection_ids: list[UUID],
) -> dict[UUID, int]:
    """Group a countable column by ``collection_id`` for the given collections."""

    rows = await session.execute(
        select(column, func.count())
        .where(column.in_(collection_ids), extra_filter)
        .group_by(column)
    )
    return {collection_id: int(count) for collection_id, count in rows}


async def _count_documents_by_collection(
    session: AsyncSession,
    collection_ids: list[UUID],
) -> dict[UUID, int]:
    """Count non-deleted documents per collection via their source."""

    rows = await session.execute(
        select(Source.collection_id, func.count())
        .join(Document, Document.source_id == Source.id)
        .where(Source.collection_id.in_(collection_ids), Source.deleted_at.is_(None))
        .group_by(Source.collection_id)
    )
    return {collection_id: int(count) for collection_id, count in rows}


async def _count_chunks_by_collection(
    session: AsyncSession,
    collection_ids: list[UUID],
) -> dict[UUID, int]:
    """Count chunks per collection, joining chunks through documents and sources."""

    rows = await session.execute(
        select(Source.collection_id, func.count())
        .select_from(Chunk)
        .join(Document, Chunk.document_id == Document.id)
        .join(Source, Document.source_id == Source.id)
        .where(Source.collection_id.in_(collection_ids), Source.deleted_at.is_(None))
        .group_by(Source.collection_id)
    )
    return {collection_id: int(count) for collection_id, count in rows}
