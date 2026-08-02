"""Suffix-based parser dispatch built on automatic subclass registration."""

from pathlib import Path

from app.rag.parsers.base import BaseParser, ParseResult


class UnsupportedFileTypeError(ValueError):
    """Raised when no registered parser supports a file's suffix."""

    def __init__(self, suffix: str, supported_suffixes: tuple[str, ...]) -> None:
        display_suffix = suffix or "(no extension)"
        supported = ", ".join(supported_suffixes) or "(none registered)"
        super().__init__(f"Unsupported file type: {display_suffix}. Supported formats: {supported}")
        self.suffix = suffix
        self.supported_suffixes = supported_suffixes


class ParserFactory:
    """Create parser instances without maintaining a manual format mapping."""

    @classmethod
    def get_parser(cls, file_path: str | Path) -> BaseParser:
        suffix = Path(file_path).suffix.casefold()
        parser_class = BaseParser.parser_for_suffix(suffix)
        if parser_class is None:
            raise UnsupportedFileTypeError(suffix, cls.supported_suffixes())
        return parser_class()

    @staticmethod
    def supported_suffixes() -> tuple[str, ...]:
        return tuple(sorted(BaseParser.registered_parsers()))


def parse_file(file_path: str | Path) -> ParseResult:
    """Parse a file with the registered parser selected from its suffix."""

    path = Path(file_path)
    return ParserFactory.get_parser(path).parse(path)
