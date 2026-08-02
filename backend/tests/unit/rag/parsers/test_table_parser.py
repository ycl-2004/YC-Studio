"""Tests for dependency-free table serialization."""

from app.rag.parsers.table_parser import rows_to_markdown


def test_rows_to_markdown_escapes_cells_and_pads_ragged_rows() -> None:
    markdown = rows_to_markdown([["key", "value"], ["a|b", "line 1\nline 2"], ["only"]])

    assert "| key | value |" in markdown
    assert "| a\\|b | line 1<br>line 2 |" in markdown
    assert markdown.endswith("| only |  |")
