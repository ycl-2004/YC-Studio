"""Small table-to-Markdown helpers shared by document parsers."""

from collections.abc import Iterable


def _escape_cell(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>").strip()


def rows_to_markdown(rows: Iterable[Iterable[str]]) -> str:
    """Approximate a rectangular table as Markdown without a pandas dependency."""

    normalized_rows = [[_escape_cell(cell) for cell in row] for row in rows]
    if not normalized_rows:
        return ""

    width = max(len(row) for row in normalized_rows)
    if width == 0:
        return ""

    padded_rows = [row + [""] * (width - len(row)) for row in normalized_rows]
    header, *body = padded_rows
    lines = [
        f"| {' | '.join(header)} |",
        f"| {' | '.join(['---'] * width)} |",
    ]
    lines.extend(f"| {' | '.join(row)} |" for row in body)
    return "\n".join(lines)
