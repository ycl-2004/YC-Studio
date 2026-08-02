"""Tests for parser contracts, automatic registration, and dispatch."""

from pathlib import Path

import pytest
from pytest import MonkeyPatch

from app.rag.parsers import (
    BaseParser,
    MarkdownParser,
    ParseResult,
    ParserFactory,
    ParserRegistrationError,
    UnsupportedFileTypeError,
)


def _isolate_registry(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(BaseParser, "_registry", dict(BaseParser.registered_parsers()))


def test_new_parser_subclass_registers_without_factory_changes(monkeypatch: MonkeyPatch) -> None:
    _isolate_registry(monkeypatch)

    class CSVParser(BaseParser):
        supported_suffixes = frozenset({"CSV"})

        def parse(self, file_path: Path) -> ParseResult:
            return ParseResult(
                text=file_path.read_text(),
                title=file_path.stem,
                meta={},
                parser_version="csv-test-v1",
            )

    parser = ParserFactory.get_parser("records.CSV")

    assert isinstance(parser, CSVParser)
    assert ".csv" in ParserFactory.supported_suffixes()


def test_duplicate_suffix_registration_is_rejected(monkeypatch: MonkeyPatch) -> None:
    _isolate_registry(monkeypatch)

    class FirstParser(BaseParser):
        supported_suffixes = frozenset({".collision"})

        def parse(self, file_path: Path) -> ParseResult:
            raise NotImplementedError

    with pytest.raises(ParserRegistrationError, match="already registered"):

        class SecondParser(BaseParser):
            supported_suffixes = frozenset({"collision"})

            def parse(self, file_path: Path) -> ParseResult:
                raise NotImplementedError


def test_factory_dispatch_is_case_insensitive() -> None:
    assert isinstance(ParserFactory.get_parser("README.MD"), MarkdownParser)


def test_unknown_format_lists_supported_suffixes() -> None:
    with pytest.raises(UnsupportedFileTypeError) as captured:
        ParserFactory.get_parser("spreadsheet.xlsx")

    message = str(captured.value)
    assert ".xlsx" in message
    assert ".md" in message
    assert ".pdf" in message
    assert ".txt" in message


def test_file_without_suffix_has_clear_error() -> None:
    with pytest.raises(UnsupportedFileTypeError, match="no extension"):
        ParserFactory.get_parser("README")
