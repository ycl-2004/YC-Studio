"""Tests for TXT, Markdown, and optional HTML parsing."""

from app.rag.parsers import HTMLParser, TextParser, parse_file


def test_text_parser_detects_non_utf8_encoding(tmp_path) -> None:
    source = tmp_path / "中文资料.txt"
    expected = "中文编码检测内容。" * 40
    source.write_bytes(expected.encode("gb18030"))

    result = TextParser().parse(source)

    assert result.text == expected
    assert result.title == "中文资料"
    assert result.parser_version == "txt-v1"
    confidence = result.meta["encoding_confidence"]
    assert isinstance(confidence, float)
    assert confidence > 0


def test_markdown_parser_preserves_structure_and_uses_h1_title(tmp_path) -> None:
    source = tmp_path / "notes.md"
    source.write_text("# 项目标题\n\n## 小节\n\n- 第一项\n- 第二项", encoding="utf-8")

    result = parse_file(source)

    assert result.title == "项目标题"
    assert "## 小节" in result.text
    assert "- 第一项" in result.text
    assert result.parser_version == "markdown-v1"


def test_html_parser_converts_headings_and_tables_to_markdown(tmp_path) -> None:
    source = tmp_path / "page.html"
    source.write_text(
        "<h1>HTML 标题</h1><table><tr><th>键</th><th>值</th></tr>"
        "<tr><td>模型</td><td>YC</td></tr></table>",
        encoding="utf-8",
    )

    result = HTMLParser().parse(source)

    assert result.title == "HTML 标题"
    assert "# HTML 标题" in result.text
    assert "模型" in result.text
    assert result.meta["source_format"] == "html"
