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

from app.db.models.chunk import Chunk
from app.db.models.collection import Collection, CollectionKind, CollectionScope
from app.db.models.document import Document
from app.db.models.ingest_batch import IngestBatch
from app.db.models.source import IngestStatus, Source
from app.rag.retriever.embeddings import get_local_embedding
from app.schemas.kb import SearchRequest
from app.services.ingest_service import IngestResult, compute_content_hash, ingest_document

_SEARCHABLE_KINDS = frozenset({CollectionKind.CASE, CollectionKind.MATERIAL})


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
        existing = await session.scalar(
            select(Source.id).where(
                Source.collection_id == collection.id,
                Source.content_hash == content_hash,
                Source.deleted_at.is_(None),
            )
        )
        if existing is not None:
            raise ValueError("This collection already contains one of the uploaded files.")
        source = Source(
            collection_id=collection.id,
            batch_id=batch.id,
            filename=upload.filename,
            content_hash=content_hash,
            dir_path=_normalise_dir_path(upload.dir_path),
            ingest_status=IngestStatus.PENDING,
        )
        session.add(source)
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


class SourceNotFoundError(LookupError):
    """The requested source does not exist."""


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

    The unique constraint ``uq_kb_collections_owner_kind_name`` (with
    ``nulls_not_distinct``) blocks a duplicate; surface it as a clean error rather
    than letting the raw IntegrityError escape to a 500.
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
        raise CollectionAlreadyExistsError(
            f"A private {kind.value} collection named {name!r} already exists"
        ) from error
    return collection


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
