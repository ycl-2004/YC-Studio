"""Plain-text parsing with explicit character-encoding detection."""

from pathlib import Path

import chardet

from app.rag.parsers.base import BaseParser, ParseResult


class TextDecodingError(ValueError):
    """Raised when detected text bytes cannot be decoded safely."""


def decode_text_bytes(data: bytes) -> tuple[str, str, float]:
    """Decode bytes using chardet's detected encoding and return its confidence."""

    if not data:
        return "", "utf-8", 1.0

    detection = chardet.detect(data)
    encoding = detection.get("encoding") or "utf-8"
    confidence = float(detection.get("confidence") or 0.0)
    try:
        return data.decode(encoding), encoding, confidence
    except (LookupError, UnicodeDecodeError) as error:
        raise TextDecodingError(
            f"Unable to decode text using detected encoding {encoding!r}"
        ) from error


class TextParser(BaseParser):
    """Parse TXT files without cleaning or chunking their contents."""

    supported_suffixes = frozenset({".txt"})

    def parse(self, file_path: Path) -> ParseResult:
        text, encoding, confidence = decode_text_bytes(file_path.read_bytes())
        return ParseResult(
            text=text,
            title=file_path.stem,
            meta={
                "encoding": encoding,
                "encoding_confidence": confidence,
                "source_path": str(file_path),
            },
            parser_version="txt-v1",
        )
