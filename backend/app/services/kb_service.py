"""Knowledge-base use cases kept independent from FastAPI request objects.

Vector distance uses pgvector's cosine-distance operator.  Stored embeddings and
query vectors are normalized, so ``1 - distance / 2`` maps cosine similarity from
[-1, 1] to the API's documented [0, 1] score range.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chunk import Chunk
from app.db.models.collection import Collection, CollectionKind, CollectionScope
from app.db.models.document import Document
from app.db.models.source import Source
from app.rag.retriever.embeddings import get_local_embedding
from app.schemas.kb import SearchRequest
from app.services.ingest_service import IngestResult, ingest_document

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
