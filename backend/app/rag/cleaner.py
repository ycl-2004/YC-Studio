"""Deterministic text cleanup that preserves Markdown structure."""

import re
import unicodedata
from collections import Counter

_ZERO_WIDTH = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")
_EXCESS_BLANK_LINES = re.compile(r"\n[ \t]*\n(?:[ \t]*\n)+")
_PAGE_NUMBER_LINE = re.compile(
    r"^(?:第\s*\d+\s*页|Page\s+\d+|\d+\s*/\s*\d+)$",
    re.IGNORECASE,
)


class TextCleaner:
    """Normalize parser output without flattening headings or lists."""

    def clean(self, text: str) -> str:
        normalized = unicodedata.normalize("NFKC", text).replace("\r\n", "\n").replace("\r", "\n")
        without_margins = self._remove_repeated_page_margins(normalized)
        without_invisible = _ZERO_WIDTH.sub("", without_margins)
        without_controls = "".join(
            character
            for character in without_invisible
            if character in {"\n", "\t", "\f"} or unicodedata.category(character) != "Cc"
        )
        lines = [
            stripped
            for line in without_controls.split("\n")
            if not _PAGE_NUMBER_LINE.fullmatch(stripped := re.sub(r"[ \t]+$", "", line).strip())
            or not stripped
        ]
        collapsed = _EXCESS_BLANK_LINES.sub("\n\n", "\n".join(lines))
        return collapsed.strip()

    @staticmethod
    def _remove_repeated_page_margins(text: str) -> str:
        pages = text.split("\f")
        if len(pages) < 2:
            return text

        page_lines = [page.splitlines() for page in pages]
        first_lines = Counter(TextCleaner._first_content_line(lines) for lines in page_lines)
        last_lines = Counter(TextCleaner._last_content_line(lines) for lines in page_lines)
        threshold = max(2, (len(pages) + 1) // 2)
        repeated_headers = {
            line for line, count in first_lines.items() if line and count >= threshold
        }
        repeated_footers = {
            line for line, count in last_lines.items() if line and count >= threshold
        }

        cleaned_pages: list[str] = []
        for lines in page_lines:
            cleaned_lines = list(lines)
            TextCleaner._remove_first_matching_line(cleaned_lines, repeated_headers)
            TextCleaner._remove_last_matching_line(cleaned_lines, repeated_footers)
            cleaned_pages.append("\n".join(cleaned_lines).strip())
        return "\n\n".join(page for page in cleaned_pages if page)

    @staticmethod
    def _first_content_line(lines: list[str]) -> str:
        return next((line.strip() for line in lines if line.strip()), "")

    @staticmethod
    def _last_content_line(lines: list[str]) -> str:
        return next((line.strip() for line in reversed(lines) if line.strip()), "")

    @staticmethod
    def _remove_first_matching_line(lines: list[str], candidates: set[str]) -> None:
        for index, line in enumerate(lines):
            if not line.strip():
                continue
            if line.strip() in candidates:
                lines.pop(index)
            return

    @staticmethod
    def _remove_last_matching_line(lines: list[str], candidates: set[str]) -> None:
        for index in range(len(lines) - 1, -1, -1):
            if not lines[index].strip():
                continue
            if lines[index].strip() in candidates:
                lines.pop(index)
            return
