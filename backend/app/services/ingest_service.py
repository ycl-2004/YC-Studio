"""Collection-aware orchestration for the ingestion pipeline."""

from app.db.models.collection import CollectionKind
from app.rag.chunker import Chunk, TextChunker

_WHOLE_DOCUMENT_KINDS = frozenset({CollectionKind.RULE, CollectionKind.TEMPLATE})


def chunk_for_collection(
    text: str,
    kind: CollectionKind,
    chunker: TextChunker,
) -> list[Chunk]:
    """Apply four-layer knowledge-base chunking policy to cleaned document text."""

    if kind in _WHOLE_DOCUMENT_KINDS:
        return chunker.preserve_as_single_chunk(text)
    return chunker.split(text)
