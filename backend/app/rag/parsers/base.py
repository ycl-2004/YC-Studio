"""Shared parser contracts and subclass registration."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from inspect import isabstract
from pathlib import Path
from types import MappingProxyType
from typing import ClassVar


@dataclass(frozen=True, slots=True)
class ParseResult:
    """Format-neutral output produced by every document parser."""

    text: str
    title: str
    meta: dict[str, object]
    parser_version: str


class ParserRegistrationError(ValueError):
    """Raised when two concrete parsers claim the same file suffix."""


class BaseParser(ABC):
    """Parse one file format and register concrete subclasses by suffix."""

    supported_suffixes: ClassVar[frozenset[str]] = frozenset()
    _registry: ClassVar[dict[str, type["BaseParser"]]] = {}

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if isabstract(cls):
            return

        normalized_suffixes = frozenset(
            cls._normalize_suffix(suffix) for suffix in cls.supported_suffixes
        )
        if not normalized_suffixes:
            raise ParserRegistrationError(
                f"{cls.__name__} must declare at least one supported suffix"
            )

        for suffix in normalized_suffixes:
            registered = BaseParser._registry.get(suffix)
            if registered is not None and registered is not cls:
                raise ParserRegistrationError(
                    f"Suffix {suffix!r} is already registered by {registered.__name__}"
                )
            BaseParser._registry[suffix] = cls

        cls.supported_suffixes = normalized_suffixes

    @staticmethod
    def _normalize_suffix(suffix: str) -> str:
        normalized = suffix.strip().casefold()
        if not normalized:
            raise ParserRegistrationError("Parser suffix cannot be empty")
        return normalized if normalized.startswith(".") else f".{normalized}"

    @classmethod
    def registered_parsers(cls) -> MappingProxyType[str, type["BaseParser"]]:
        """Return a read-only view of the current suffix registry."""

        return MappingProxyType(cls._registry)

    @classmethod
    def parser_for_suffix(cls, suffix: str) -> type["BaseParser"] | None:
        """Return the registered parser class for a normalized suffix."""

        if not suffix:
            return None
        return cls._registry.get(cls._normalize_suffix(suffix))

    @abstractmethod
    def parse(self, file_path: Path) -> ParseResult:
        """Parse a local file into the shared result contract."""
