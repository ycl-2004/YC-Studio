"""Tests for the PDF parser boundary without loading Docling models."""

from pathlib import Path
from typing import cast

import pytest

from app.rag.parsers import NoTextLayerError, PDFParser
from app.rag.parsers.pdf_parser import _ConversionResult, _DocumentConverter


class FakeDocument:
    def __init__(self, plain_text: str, markdown: str) -> None:
        self.pages = {1: object(), 2: object()}
        self.tables = [object()]
        self.plain_text = plain_text
        self.markdown = markdown
        self.markdown_options: dict[str, object] = {}

    def export_to_text(self, **kwargs: object) -> str:
        return self.plain_text

    def export_to_markdown(self, **kwargs: object) -> str:
        self.markdown_options = kwargs
        return self.markdown


class FakeResult:
    def __init__(self, document: FakeDocument) -> None:
        self.document = document


class FakeConverter:
    def __init__(self, document: FakeDocument) -> None:
        self.document = document
        self.source: Path | str | None = None

    def convert(self, source: Path | str) -> _ConversionResult:
        self.source = source
        return cast(_ConversionResult, FakeResult(self.document))


def test_pdf_parser_returns_markdown_and_provenance(tmp_path) -> None:
    source = tmp_path / "guide.pdf"
    document = FakeDocument("正文", "# 正文\n\n| 键 | 值 |")
    converter = FakeConverter(document)

    result = PDFParser(converter=cast(_DocumentConverter, converter)).parse(source)

    assert converter.source == source
    assert result.text.startswith("# 正文")
    assert result.meta["page_count"] == 2
    assert result.meta["table_count"] == 1
    assert result.meta["ocr_enabled"] is False
    assert document.markdown_options["page_break_placeholder"] == "\f"


def test_pdf_parser_rejects_scan_without_text_layer(tmp_path) -> None:
    source = tmp_path / "scan.pdf"
    converter = FakeConverter(FakeDocument("  ", "<!-- image -->"))
    parser = PDFParser(converter=cast(_DocumentConverter, converter))

    with pytest.raises(NoTextLayerError, match="no extractable text layer"):
        parser.parse(source)
