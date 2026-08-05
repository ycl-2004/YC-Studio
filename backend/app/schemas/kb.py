"""Request and response contracts for knowledge-base HTTP endpoints."""

import enum
from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field

from app.db.models.collection import CollectionKind, CollectionScope
from app.db.models.source import IngestStatus


class UploadResponse(BaseModel):
    """The persisted outcome of one synchronous knowledge-base upload."""

    source_id: UUID
    document_id: UUID | None
    chunk_count: Annotated[int, Field(ge=0)]
    skipped: bool


class BatchUploadResponse(BaseModel):
    """Immediate acknowledgement for files persisted for asynchronous ingest."""

    batch_id: UUID
    source_ids: list[UUID]
    total: Annotated[int, Field(ge=1)]


class BatchProgressResponse(BaseModel):
    """The database-backed processing state for one batch upload."""

    batch_id: UUID
    total: Annotated[int, Field(ge=0)]
    completed: Annotated[int, Field(ge=0)]
    failed: Annotated[int, Field(ge=0)]
    in_progress: Annotated[int, Field(ge=0)]
    pending: Annotated[int, Field(ge=0)]


class SearchRequest(BaseModel):
    """A vector search restricted to one searchable library kind."""

    query: Annotated[str, Field(min_length=1, max_length=2_000)]
    kind: CollectionKind
    top_k: Annotated[int, Field(default=5, ge=1, le=20)] = 5
    metadata_filter: dict[str, str] = Field(default_factory=dict)


class SearchDocument(BaseModel):
    """Original parsed document information for a retrieved chunk."""

    id: UUID
    title: str


class SearchSource(BaseModel):
    """Original uploaded source information for a retrieved chunk."""

    id: UUID
    filename: str


class SearchResult(BaseModel):
    """One retrieved chunk with its source trail and normalized relevance score."""

    chunk_id: UUID
    text: str
    score: Annotated[
        float,
        Field(
            ge=0,
            le=1,
            description=(
                "Cosine similarity normalized from [-1, 1] to [0, 1]; higher is more relevant."
            ),
        ),
    ]
    document: SearchDocument
    source: SearchSource


class SearchResponse(BaseModel):
    """Vector retrieval results in descending relevance order."""

    results: list[SearchResult]


class CollectionSummary(BaseModel):
    """One knowledge-base library the current user can see or write to."""

    id: UUID
    kind: CollectionKind
    scope: CollectionScope
    name: str
    source_count: Annotated[int, Field(ge=0)]
    document_count: Annotated[int, Field(ge=0)]
    chunk_count: Annotated[int, Field(ge=0)]


class CollectionListResponse(BaseModel):
    """All collections (public plus the user's private ones) with live counts."""

    collections: list[CollectionSummary]


class CreateCollectionRequest(BaseModel):
    """Payload to create a private collection owned by the current user."""

    kind: CollectionKind
    name: Annotated[str, Field(min_length=1, max_length=200)]


class CollectionResponse(BaseModel):
    """A single collection's metadata."""

    id: UUID
    kind: CollectionKind
    scope: CollectionScope
    name: str
    user_id: UUID | None


class SourceSummary(BaseModel):
    """One uploaded source (document) with its ingest status and chunk count."""

    source_id: UUID
    filename: str
    ingest_status: IngestStatus
    dir_path: str | None
    created_at: datetime
    document_id: UUID | None
    title: str | None
    chunk_count: Annotated[int, Field(ge=0)]


class SourceListResponse(BaseModel):
    """Uploaded sources (documents) in a collection, newest first."""

    sources: list[SourceSummary]


class SourcePreviewMode(enum.StrEnum):
    """How a client should render the original file, decided from its suffix."""

    TEXT = "text"
    PDF = "pdf"
    DOWNLOAD = "download"


class SourceChunkPreview(BaseModel):
    """One stored chunk in document order, without its embedding vector."""

    chunk_id: UUID
    ordinal: int
    text: str
    token_count: Annotated[int, Field(ge=0)]


class SourcePreviewResponse(BaseModel):
    """Everything the management UI shows for one uploaded file.

    ``raw_text`` is the parsed document text, which exists for every completed source.
    ``original_available`` reports whether the uploaded bytes themselves are still on
    disk and can be fetched from the file endpoint — public seed libraries and older
    synchronous uploads have parsed text but no stored original.
    """

    source_id: UUID
    filename: str
    suffix: str
    media_type: Annotated[
        str,
        Field(description="The Content-Type the file endpoint serves this source with."),
    ]
    preview_mode: SourcePreviewMode
    ingest_status: IngestStatus
    dir_path: str | None
    created_at: datetime
    error_message: str | None

    original_available: bool
    size_bytes: Annotated[int, Field(ge=0)] | None

    document_id: UUID | None
    title: str | None
    raw_text: str | None
    raw_text_truncated: bool
    chunk_count: Annotated[int, Field(ge=0)]
    chunks: list[SourceChunkPreview]
    chunks_truncated: bool
