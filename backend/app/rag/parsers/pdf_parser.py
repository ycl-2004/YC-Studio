"""PDF parsing through Docling with OCR intentionally disabled."""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol, cast

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

from app.rag.parsers.base import BaseParser, ParseResult


class NoTextLayerError(ValueError):
    """Raised when a PDF has no extractable programmatic text layer."""


class _DoclingDocument(Protocol):
    pages: Mapping[int, object]
    tables: Sequence[object]

    def export_to_text(self, **kwargs: object) -> str: ...

    def export_to_markdown(self, **kwargs: object) -> str: ...


class _ConversionResult(Protocol):
    document: _DoclingDocument


class _DocumentConverter(Protocol):
    def convert(self, source: Path | str) -> _ConversionResult: ...


def _build_converter() -> _DocumentConverter:
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = False
    pipeline_options.do_table_structure = True
    pipeline_options.force_backend_text = True

    # Docling's documented PDF customization uses InputFormat.PDF + PdfFormatOption.
    # Source: https://docling-project.github.io/docling/reference/document_converter/
    converter = DocumentConverter(
        allowed_formats=[InputFormat.PDF],
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
        },
    )
    return cast(_DocumentConverter, converter)


class PDFParser(BaseParser):
    """Parse text-layer PDFs while retaining Docling's Markdown tables."""

    supported_suffixes = frozenset({".pdf"})

    def __init__(self, converter: _DocumentConverter | None = None) -> None:
        self._converter = converter or _build_converter()

    def parse(self, file_path: Path) -> ParseResult:
        result = self._converter.convert(file_path)
        document = result.document
        plain_text = document.export_to_text().strip()
        if not plain_text:
            raise NoTextLayerError(
                f"PDF has no extractable text layer: {file_path.name}. OCR is not enabled."
            )

        # Page markers let the separate cleaner detect repeated headers/footers later.
        # Source: https://docling-project.github.io/docling/reference/docling_document/
        text = document.export_to_markdown(
            image_placeholder="",
            page_break_placeholder="\f",
        ).strip()
        return ParseResult(
            text=text,
            title=file_path.stem,
            meta={
                "source_path": str(file_path),
                "page_count": len(document.pages),
                "table_count": len(document.tables),
                "ocr_enabled": False,
            },
            parser_version="pdf-docling-v1",
        )
