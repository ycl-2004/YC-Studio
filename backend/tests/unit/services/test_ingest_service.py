"""Tests for collection-aware ingestion chunking policy."""

import pytest

from app.db.models.collection import CollectionKind
from app.rag.chunker import TextChunker
from app.services.ingest_service import chunk_for_collection


def count_characters(text: str) -> int:
    return len(text)


@pytest.mark.parametrize("kind", [CollectionKind.RULE, CollectionKind.TEMPLATE])
def test_rule_and_template_collections_preserve_the_complete_document(
    kind: CollectionKind,
) -> None:
    text = "# 完整文档\n\n" + "不能拆分。" * 20
    chunker = TextChunker(count_characters, max_tokens=20, overlap_tokens=2)

    chunks = chunk_for_collection(text, kind, chunker)

    assert len(chunks) == 1
    assert chunks[0].text == text
    assert chunks[0].token_count == count_characters(text)


@pytest.mark.parametrize("kind", [CollectionKind.CASE, CollectionKind.MATERIAL])
def test_case_and_material_collections_use_normal_chunking(kind: CollectionKind) -> None:
    text = "第一句内容。第二句内容。第三句内容。第四句内容。"
    chunker = TextChunker(count_characters, max_tokens=12, overlap_tokens=2)

    chunks = chunk_for_collection(text, kind, chunker)

    assert len(chunks) > 1
    assert all(chunk.token_count <= 12 for chunk in chunks)
