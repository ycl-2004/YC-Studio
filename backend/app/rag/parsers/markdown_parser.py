"""Markdown parser that preserves source structure for later chunking."""

from pathlib import Path

from app.rag.parsers.base import BaseParser, ParseResult
from app.rag.parsers.txt_parser import decode_text_bytes


def title_from_markdown(text: str, fallback: str) -> str:
    """Use the first level-one Markdown heading when one exists."""

    for line in text.splitlines():
        if line.startswith("# ") and line[2:].strip():
            return line[2:].strip()
    return fallback


class MarkdownParser(BaseParser):
    """Parse Markdown while leaving headings and lists unchanged."""

    supported_suffixes = frozenset({".md", ".markdown"})

    def parse(self, file_path: Path) -> ParseResult:
        text, encoding, confidence = decode_text_bytes(file_path.read_bytes())
        return ParseResult(
            text=text,
            title=title_from_markdown(text, file_path.stem),
            meta={
                "encoding": encoding,
                "encoding_confidence": confidence,
                "source_path": str(file_path),
            },
            parser_version="markdown-v1",
        )
