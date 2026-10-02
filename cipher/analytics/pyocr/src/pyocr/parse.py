"""Parse DeepSeek-OCR-family output (jina-ocr-v1) into page markdown, tables, and figure regions.

* Tables arrive as HTML `<table>`; they become `ExtractedTableInfo` (cells + markdown) and are
  swapped for pipe tables in the page markdown so chunks don't carry tag noise.
* Figures only appear with `FIGURE_PROMPT`, as `<|ref|>caption<|/ref|><|det|>[[x1,y1,x2,y2]]<|/det|>`
  in 1000 bins (0-999). They become `OcrRegion`s with the shared normalized `BoundingBox`. The
  caption is the model's description, not document text, so it stays on the region and out of
  the searchable markdown.
"""

import json
import re
from html.parser import HTMLParser

from cipher.schemas._base.detection import BoundingBox
from cipher.schemas.content.document import ExtractedTableInfo
from pyocr.schemas import OcrPage, OcrRegion

DEFAULT_PROMPT = (
    "Transcribe the provided document image into a clean Markdown format, preserving the natural reading order."
)
# DeepSeek-OCR's grounding prompt: plainer text, but figures come back located + captioned.
FIGURE_PROMPT = "<|grounding|>OCR this image."

_COORD_BINS = 999
_REF_DET_RE = re.compile(r"<\|ref\|>(.*?)<\|/ref\|><\|det\|>(.*?)<\|/det\|>", re.DOTALL)
_MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]*?(\d+)_(\d+)_(\d+)_(\d+)\.(?:png|jpe?g)\)")
# Any other image reference (e.g. `![image](image_placeholder)`) has no location to keep.
_UNLOCATED_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_SPECIAL_TOKENS_RE = re.compile(r"<｜end▁of▁sentence｜>|<｜▁pad▁｜>|<image>")
_TABLE_RE = re.compile(r"<table\b.*?</table>", re.DOTALL | re.IGNORECASE)
_EMPTY_OUTPUTS = frozenset({"", "null", "none"})


class _TableParser(HTMLParser):
    """HTML table -> row-major cells; colspan pads, rowspan carries the value down."""

    def __init__(self):
        super().__init__()
        self.rows: list[list[str]] = []
        self._carried: dict[int, tuple[str, int]] = {}
        self._cell: list[str] | None = None
        self._span = (1, 1)

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.rows.append([])
        elif tag in ("td", "th") and self.rows:
            attributes = dict(attrs)
            self._cell = []
            self._span = (int(attributes.get("colspan") or 1), int(attributes.get("rowspan") or 1))
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if tag not in ("td", "th") or self._cell is None:
            return
        row = self.rows[-1]
        self._fill_carried(row)
        text = " ".join("".join(self._cell).split())
        colspan, rowspan = self._span
        for offset in range(colspan):
            if rowspan > 1:
                self._carried[len(row)] = (text if offset == 0 else "", rowspan - 1)
            row.append(text if offset == 0 else "")
        self._cell = None

    def _fill_carried(self, row: list[str]):
        while len(row) in self._carried:
            text, remaining = self._carried.pop(len(row))
            if remaining > 1:
                self._carried[len(row)] = (text, remaining - 1)
            row.append(text)

    def cells(self) -> list[list[str]]:
        rows = [row for row in self.rows if any(row)]
        width = max((len(row) for row in rows), default=0)
        return [row + [""] * (width - len(row)) for row in rows]


def cells_to_markdown(cells: list[list[str]]) -> str:
    """Render row-major cells as a pipe table (first row is the header)."""
    header, *rows = [[c.replace("|", "\\|") for c in row] for row in cells]
    lines = [f"| {' | '.join(header)} |", f"| {' | '.join(['---'] * len(header))} |"]
    lines.extend(f"| {' | '.join(row)} |" for row in rows)
    return "\n".join(lines)


def _extract_tables(text: str, page_number: int) -> tuple[str, list[ExtractedTableInfo]]:
    tables = []

    def replace(match: re.Match) -> str:
        parser = _TableParser()
        parser.feed(match.group(0))
        cells = parser.cells()
        if not cells:
            return ""
        markdown = cells_to_markdown(cells)
        tables.append(ExtractedTableInfo(cells=cells, markdown=markdown, page_number=page_number))
        return f"\n\n{markdown}\n\n"

    return _TABLE_RE.sub(replace, text), tables


def _bounding_box(coords: list[int]) -> BoundingBox | None:
    x1, y1, x2, y2 = (max(0.0, min(1.0, c / _COORD_BINS)) for c in coords)
    if x2 <= x1 or y2 <= y1:
        return None
    return BoundingBox(xmin=x1, ymin=y1, xmax=x2, ymax=y2)


def _parse_coords(literal: str) -> list[list[int]]:
    try:
        return [[int(c) for c in box] for box in json.loads(literal) if len(box) == 4]
    except (ValueError, TypeError):
        return []


def _extract_figures(text: str) -> tuple[str, list[OcrRegion]]:
    regions = []

    def replace(match: re.Match) -> str:
        caption = match.group(1).strip()
        for coords in _parse_coords(match.group(2)):
            if box := _bounding_box(coords):
                regions.append(OcrRegion(label="figure", text=caption or None, bounding_box=box))
        return ""

    def markdown_image(match: re.Match) -> str:
        caption, *coords = match.groups()
        return f"<|ref|>{caption}<|/ref|><|det|>[[{','.join(coords)}]]<|/det|>"

    text = _REF_DET_RE.sub(replace, _MARKDOWN_IMAGE_RE.sub(markdown_image, text))
    return _UNLOCATED_IMAGE_RE.sub("", text), regions


_RUNAWAY_MAX_PERIOD = 400
_RUNAWAY_MIN_REPEATS = 4
_RUNAWAY_MIN_CHARS = 200


def trim_runaway(text: str) -> tuple[str, bool]:
    """Cut a decoding loop off the end of `text`, keeping one copy of the repeated unit.

    A page that makes the model loop (an empty table header, a boilerplate line) runs
    to the token cap repeating itself -- sometimes text that isn't on the page at all.
    The loop shows as a tail that repeats with a fixed period.
    """
    for period in range(1, min(_RUNAWAY_MAX_PERIOD, len(text) // _RUNAWAY_MIN_REPEATS) + 1):
        span = max(period * _RUNAWAY_MIN_REPEATS, _RUNAWAY_MIN_CHARS)
        if span + period > len(text) or text[-span:] != text[-span - period : -period]:
            continue
        start = len(text) - span - period
        while start > 0 and text[start - 1] == text[start - 1 + period]:
            start -= 1
        return text[: start + period].rstrip(), True
    return text, False


def parse_page(raw: str, page_number: int) -> OcrPage:
    """Split one page's raw model output into clean markdown, tables, and figure regions."""
    text, is_truncated = trim_runaway(_SPECIAL_TOKENS_RE.sub("", raw).strip())
    if text.lower() in _EMPTY_OUTPUTS:
        return OcrPage(page_number=page_number, markdown="")
    text, regions = _extract_figures(text)
    text, tables = _extract_tables(text, page_number=page_number)
    markdown = re.sub(r"\n{3,}", "\n\n", text).strip()
    if markdown.lower() in _EMPTY_OUTPUTS:
        markdown = ""
    return OcrPage(
        page_number=page_number, markdown=markdown, tables=tables, regions=regions, is_truncated=is_truncated
    )
