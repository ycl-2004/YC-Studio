"""Token-counted recursive text chunking independent of a tokenizer vendor."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Chunk:
    """One ordered, token-counted retrieval unit."""

    ordinal: int
    text: str
    token_count: int


class TextChunker:
    """Split text recursively while measuring every boundary in tokens."""

    # PDF extraction can insert visual paragraph and line breaks inside a sentence. Keep
    # Markdown section boundaries first, then prefer sentence punctuation over visual wraps.
    DEFAULT_SEPARATORS = (
        "\n## ",
        "。",
        "！",
        "？",
        "? ",
        "! ",
        ". ",
        "\n\n",
        "\n",
        " ",
    )

    def __init__(
        self,
        count_tokens: Callable[[str], int],
        *,
        max_tokens: int = 512,
        overlap_tokens: int = 51,
        separators: Sequence[str] = DEFAULT_SEPARATORS,
    ) -> None:
        if max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if overlap_tokens < 0 or overlap_tokens >= max_tokens:
            raise ValueError("overlap_tokens must be non-negative and smaller than max_tokens")
        if not separators or any(not separator for separator in separators):
            raise ValueError("separators must contain non-empty strings")

        self._count_tokens = count_tokens
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens
        self.separators = tuple(separators)

    def split(self, text: str) -> list[Chunk]:
        normalized = text.strip()
        if not normalized:
            return []

        pieces = self._split_to_limit(normalized, self.separators)
        chunks: list[Chunk] = []
        current = ""
        for piece in pieces:
            candidate = self._join(current, piece)
            if current and self._count_tokens(candidate) > self.max_tokens:
                chunks.append(self._make_chunk(len(chunks), current))
                overlap = self._token_limited_tail(current, self.overlap_tokens)
                candidate = self._join(overlap, piece)
                current = candidate if self._count_tokens(candidate) <= self.max_tokens else piece
            else:
                current = candidate

        if current:
            chunks.append(self._make_chunk(len(chunks), current))
        return chunks

    def preserve_as_single_chunk(self, text: str) -> list[Chunk]:
        """Return one complete chunk even when it exceeds the retrieval chunk limit."""

        normalized = text.strip()
        if not normalized:
            return []
        return [
            Chunk(
                ordinal=0,
                text=normalized,
                token_count=self._count_tokens(normalized),
            )
        ]

    def _split_to_limit(self, text: str, separators: Sequence[str]) -> list[str]:
        if self._count_tokens(text) <= self.max_tokens:
            return [text]
        if not separators:
            return self._hard_split(text)

        separator, *remaining = separators
        pieces = self._split_preserving_separator(text, separator)
        if len(pieces) == 1:
            return self._split_to_limit(text, remaining)

        result: list[str] = []
        for piece in pieces:
            result.extend(self._split_to_limit(piece.strip(), remaining))
        return [piece for piece in result if piece]

    def _hard_split(self, text: str) -> list[str]:
        pieces: list[str] = []
        remaining = text
        while remaining:
            end = self._largest_prefix_within_limit(remaining, self.max_tokens)
            if end == 0:
                raise ValueError("Tokenizer reports more than max_tokens for a single character")
            pieces.append(remaining[:end].strip())
            remaining = remaining[end:].strip()
        return [piece for piece in pieces if piece]

    def _largest_prefix_within_limit(self, text: str, token_limit: int) -> int:
        low, high = 0, len(text)
        while low < high:
            middle = (low + high + 1) // 2
            if self._count_tokens(text[:middle]) <= token_limit:
                low = middle
            else:
                high = middle - 1
        return low

    def _token_limited_tail(self, text: str, token_limit: int) -> str:
        if token_limit == 0:
            return ""
        low, high = 0, len(text)
        while low < high:
            middle = (low + high) // 2
            if self._count_tokens(text[middle:]) <= token_limit:
                high = middle
            else:
                low = middle + 1
        return text[low:].strip()

    @staticmethod
    def _split_preserving_separator(text: str, separator: str) -> list[str]:
        parts = text.split(separator)
        if len(parts) == 1:
            return [text]
        if separator in {"。", "！", "？", "? ", "! ", ". "}:
            return [part + separator for part in parts[:-1]] + [parts[-1]]
        return [parts[0]] + [separator + part for part in parts[1:]]

    @staticmethod
    def _join(left: str, right: str) -> str:
        return f"{left}\n{right}".strip() if left else right.strip()

    def _make_chunk(self, ordinal: int, text: str) -> Chunk:
        normalized = text.strip()
        token_count = self._count_tokens(normalized)
        if token_count > self.max_tokens:
            raise AssertionError("chunk exceeds configured token limit")
        return Chunk(ordinal=ordinal, text=normalized, token_count=token_count)
