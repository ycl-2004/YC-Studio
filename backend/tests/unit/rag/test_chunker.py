"""Tests for token-counted recursive chunking."""

import pytest

from app.rag.chunker import Chunk, TextChunker


def count_characters(text: str) -> int:
    """Deterministic tokenizer stand-in used only to test chunk boundaries."""

    return len(text)


def test_chunker_uses_token_counter_and_continuous_ordinals() -> None:
    text = "第一段内容比较长。第二段内容也比较长。第三段继续补充内容。第四段结束。"
    chunker = TextChunker(count_characters, max_tokens=18, overlap_tokens=3)

    chunks = chunker.split(text)

    assert len(chunks) > 1
    assert [chunk.ordinal for chunk in chunks] == list(range(len(chunks)))
    assert all(chunk.token_count == count_characters(chunk.text) for chunk in chunks)
    assert all(chunk.token_count <= 18 for chunk in chunks)


def test_chunker_preserves_short_markdown_section() -> None:
    text = "## 标题\n\n- 第一项\n- 第二项"

    chunks = TextChunker(count_characters, max_tokens=100, overlap_tokens=10).split(text)

    assert len(chunks) == 1
    assert chunks[0].text == text


def test_chunker_hard_splits_content_without_boundaries() -> None:
    chunks = TextChunker(count_characters, max_tokens=10, overlap_tokens=2).split("甲" * 25)

    assert [chunk.ordinal for chunk in chunks] == [0, 1, 2]
    assert all(chunk.token_count <= 10 for chunk in chunks)


def test_chunker_prefers_sentence_boundary_over_pdf_visual_paragraph_break() -> None:
    text = f"上一句结束。{'甲' * 15}\n\n{'乙' * 5}。下一句结束。"

    chunks = TextChunker(count_characters, max_tokens=25, overlap_tokens=0).split(text)

    assert [chunk.text[-1] for chunk in chunks] == ["。", "。", "。"]


def test_chunker_can_preserve_a_complete_document() -> None:
    text = "# 平台规则\n\n" + "规则正文。" * 20
    chunker = TextChunker(count_characters, max_tokens=20, overlap_tokens=2)

    chunks = chunker.preserve_as_single_chunk(text)

    assert chunks == [Chunk(ordinal=0, text=text, token_count=count_characters(text))]


@pytest.mark.parametrize(
    ("max_tokens", "overlap_tokens"),
    [(0, 0), (10, -1), (10, 10)],
)
def test_chunker_rejects_invalid_limits(max_tokens: int, overlap_tokens: int) -> None:
    with pytest.raises(ValueError):
        TextChunker(
            count_characters,
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens,
        )
