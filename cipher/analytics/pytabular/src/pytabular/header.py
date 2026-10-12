"""Find the header row(s) in raw rows: title rows above, two-row headers, or no header at all."""

import re
from collections import Counter
from dataclasses import dataclass

from pytabular.fields import header_synonyms, normalize_header
from pytabular.profile import is_null, is_number

SCAN_ROWS = 20
_DATEISH = re.compile(r"^\d{1,4}[-./]\d{1,2}[-./]\d{1,4}")
_VALUEISH = re.compile(r"@|^\+?\d[\d\s()\-]{6,}$|^https?://")


@dataclass(frozen=True, slots=True)
class HeaderGuess:
    header_rows: list[int]
    data_start_row: int
    names: list[str]
    width: int


def _label_like(cell: str) -> bool:
    text = cell.strip()
    return (
        bool(text)
        and len(text) <= 60
        and not is_number(text)
        and not _DATEISH.match(text)
        and not _VALUEISH.search(text)
    )


def _known_header(cell: str) -> bool:
    key = normalize_header(cell)
    return bool(key) and any(key in synonyms for synonyms in header_synonyms().values())


def _row_score(row: list[str], below: list[list[str]], width: int) -> float:
    cells = [c for c in row if c.strip()]
    if len(cells) < max(1, 0.5 * width) or len(cells) == 1 < width:
        return 0.0
    label = sum(map(_label_like, cells)) / len(cells)
    unique = len(set(cells)) / len(cells)
    known = sum(map(_known_header, cells)) / len(cells)
    # How unlike the rows underneath it is: header cells are labels where data cells are numbers / values.
    contrast = 0.0
    if below:
        data_labelish = sum(_label_like(c) for r in below for c in r if c.strip()) / max(
            sum(1 for r in below for c in r if c.strip()), 1
        )
        contrast = max(0.0, label - data_labelish)
    repeats = sum(1 for r in below if r[: len(row)] == row) / max(len(below), 1)
    return 0.35 * label + 0.15 * unique + 0.3 * known + 0.2 * contrast - repeats


def detect_header(rows: list[list[str]], *, known_names: list[str] | None = None) -> HeaderGuess:
    """Pick the header among the first rows (or none: synthetic `column_1..n`)."""
    if known_names is not None:
        return HeaderGuess(header_rows=[], data_start_row=0, names=list(known_names), width=len(known_names))
    if not rows:
        return HeaderGuess(header_rows=[], data_start_row=0, names=[], width=0)

    widths = Counter(len(r) for r in rows[: SCAN_ROWS * 5] if any(c.strip() for c in r))
    width = max(widths, key=lambda w: (widths[w], w)) if widths else max(map(len, rows))

    scored = [(i, _row_score(rows[i], rows[i + 1 : i + 11], width)) for i in range(min(SCAN_ROWS, len(rows)))]
    best, score = max(scored, key=lambda item: item[1], default=(0, 0.0))
    if score < 0.45:
        start = next((i for i, r in enumerate(rows) if sum(1 for c in r if c.strip()) >= 0.5 * width), 0)
        return HeaderGuess(
            header_rows=[], data_start_row=start, names=[f"column_{i + 1}" for i in range(width)], width=width
        )

    above = rows[best - 1] if best > 0 else []
    if above and _is_group_row(above, rows[best], width):
        best -= 1
    header_rows = [best]
    names = [c.strip() for c in _pad(rows[best], width)]
    following = rows[best + 1] if best + 1 < len(rows) else []
    # Two-row header: a grouping row with gaps (merged cells) over a full row of labels.
    if (
        any(not c.strip() for c in rows[best][:width])
        and following
        and _row_score(following, rows[best + 2 : best + 12], width) >= 0.45
    ):
        header_rows.append(best + 1)
        groups = _fill_merged(rows[best], width)
        names = [" ".join(p for p in (a, b.strip()) if p) for a, b in zip(groups, _pad(following, width), strict=True)]
    names = [n.strip() or f"column_{i + 1}" for i, n in enumerate(names)]
    return HeaderGuess(header_rows=header_rows, data_start_row=header_rows[-1] + 1, names=_dedupe(names), width=width)


def _is_group_row(row: list[str], labels: list[str], width: int) -> bool:
    """A row of group labels with gaps (merged cells) sitting over a fuller row of labels."""
    filled = [c for c in _pad(row, width) if c.strip()]
    below = sum(1 for c in _pad(labels, width) if c.strip())
    return 1 < len(filled) < below and all(map(_label_like, filled)) and _pad(row, width)[0].strip() != ""


def _pad(row: list[str], width: int) -> list[str]:
    return (row + [""] * width)[:width]


def _fill_merged(row: list[str], width: int) -> list[str]:
    """Forward-fill gaps after a label (an Excel merged cell spanning columns)."""
    out: list[str] = []
    last = ""
    for cell in _pad(row, width):
        last = cell.strip() or last
        out.append(cell.strip() or (last if out and out[-1] else ""))
    return out


def _dedupe(names: list[str]) -> list[str]:
    seen: Counter[str] = Counter()
    out = []
    for name in names:
        seen[name] += 1
        out.append(name if seen[name] == 1 else f"{name}_{seen[name]}")
    return out


def data_rows(rows: list[list[str]], guess: HeaderGuess) -> list[list[str]]:
    """Rows after the header that aren't blank or repeats of the header."""
    header = guess.names
    return [r for r in rows if any(not is_null(c) for c in r) and r[: len(header)] != header]
