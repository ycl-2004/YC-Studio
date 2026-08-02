"""Optional HTML-to-Markdown parser retained from the earlier project."""

from pathlib import Path

from markdownify import markdownify

from app.rag.parsers.base import BaseParser, ParseResult
from app.rag.parsers.markdown_parser import title_from_markdown
from app.rag.parsers.txt_parser import decode_text_bytes


class HTMLParser(BaseParser):
    """Convert HTML into Markdown without cleaning or chunking it."""

    supported_suffixes = frozenset({".htm", ".html"})

    def parse(self, file_path: Path) -> ParseResult:
        html, encoding, confidence = decode_text_bytes(file_path.read_bytes())
        # Source: https://github.com/matthewwithanm/python-markdownify
        text = markdownify(html, heading_style="ATX").strip()
        return ParseResult(
            text=text,
            title=title_from_markdown(text, file_path.stem),
            meta={
                "encoding": encoding,
                "encoding_confidence": confidence,
                "source_path": str(file_path),
                "source_format": "html",
            },
            parser_version="html-markdownify-v1",
        )
