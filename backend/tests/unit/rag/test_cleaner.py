"""Tests for structure-preserving text cleanup."""

from app.rag.cleaner import TextCleaner


def test_cleaner_normalizes_unicode_and_removes_invisible_controls() -> None:
    source = "# ＹＣ\u200b 标题\n\n- 项目\x00一\n\n\n\n正文"

    cleaned = TextCleaner().clean(source)

    assert cleaned == "# YC 标题\n\n- 项目一\n\n正文"


def test_cleaner_removes_repeated_page_headers_and_footers() -> None:
    source = (
        "YC Studio 内部资料\n第一页正文\n第 1 页\f"
        "YC Studio 内部资料\n第二页正文\n第 2 页\f"
        "YC Studio 内部资料\n第三页正文\n第 3 页"
    )

    cleaned = TextCleaner().clean(source)

    assert "YC Studio 内部资料" not in cleaned
    assert "第 1 页" not in cleaned
    assert "第 2 页" not in cleaned
    assert "第 3 页" not in cleaned
    assert cleaned == "第一页正文\n\n第二页正文\n\n第三页正文"


def test_cleaner_does_not_remove_single_page_boundaries() -> None:
    source = "# 标题\n\n- 列表\n\n正文"

    assert TextCleaner().clean(source) == source
