"""Carry character offsets across a person's correction of a file's text.

Mentions, chunks and prechunked spans all point into `ExtractedText.content` by
character offset. When an analyst fixes OCR text those offsets have to follow the
edit, and nothing may land on the wrong words. `TextCorrection` diffs the old and
new text (lines first, then characters inside changed lines) and maps positions
through it. Only text that was not edited is moved, and every moved span is
re-checked against the new text, so a span is either placed provably or reported
as lost. It is never guessed.
"""

from collections.abc import Callable
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal

from pydantic import Field

from cipher.schemas._base.base import BaseModel, StrEnum
from cipher.schemas.ingestion.enrichment import EnrichmentType

# Above this a changed block is taken as one replacement: a character diff of a
# rewritten page costs far more than it saves.
MAX_CHAR_DIFF = 20_000

Bias = Literal["left", "right"]


class SpanFate(StrEnum):
    """What a correction did to one span."""

    MOVED = "moved"
    """Its text was untouched; only its offsets shifted."""
    EDITED = "edited"
    """Both ends survived, the text between them changed (a misspelt name fixed in place)."""
    RELOCATED = "relocated"
    """An end was edited away, but its exact text is still in the rewritten stretch."""
    LOST = "lost"
    """Its text is gone from where it was."""


@dataclass(frozen=True)
class Edit:
    """One changed stretch: `old[old_start:old_end]` became `new[new_start:new_end]` (either may be empty)."""

    old_start: int
    old_end: int
    new_start: int
    new_end: int


@dataclass(frozen=True)
class SpanMove:
    """Where a span ended up; `start`/`end` are None when `fate` is LOST."""

    fate: SpanFate
    start: int | None = None
    end: int | None = None


def _line_starts(lines: list[str]) -> list[int]:
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line))
    return starts


def diff_edits(old: str, new: str) -> tuple[list[Edit], list[Edit]]:
    """`(edits, changed_lines)`: the changed character stretches, and the whole changed lines they sit in.

    Both in order; no two edits are adjacent.
    """
    old_lines, new_lines = old.splitlines(keepends=True), new.splitlines(keepends=True)
    old_starts, new_starts = _line_starts(old_lines), _line_starts(new_lines)
    edits, changed_lines = [], []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, old_lines, new_lines, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        lines = Edit(old_start=old_starts[i1], old_end=old_starts[i2], new_start=new_starts[j1], new_end=new_starts[j2])
        changed_lines.append(lines)
        if max(lines.old_end - lines.old_start, lines.new_end - lines.new_start) > MAX_CHAR_DIFF:
            edits.append(lines)
            continue
        matcher = SequenceMatcher(
            None, old[lines.old_start : lines.old_end], new[lines.new_start : lines.new_end], autojunk=False
        )
        edits.extend(
            Edit(
                old_start=lines.old_start + x1,
                old_end=lines.old_start + x2,
                new_start=lines.new_start + y1,
                new_end=lines.new_start + y2,
            )
            for op, x1, x2, y1, y2 in matcher.get_opcodes()
            if op != "equal"
        )
    return edits, changed_lines


def merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Sort and join ranges that overlap or touch."""
    merged: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def touches(start: int, end: int, ranges: list[tuple[int, int]]) -> bool:
    """Whether `[start, end)` overlaps or borders any range. A pure deletion is a zero-width range."""
    return any(start <= range_end and end >= range_start for range_start, range_end in ranges)


def correction_filter(
    *, corrected_ranges: list[tuple[int, int]], taken: list[tuple[int, int]]
) -> Callable[[int, int], bool]:
    """Which spans an extractor re-running over a corrected text may add.

    Only spans inside what a person wrote, never over a mention already there. Untouched
    text keeps the mentions it had, including the ones an analyst deleted.
    """

    def keep(start: int, end: int) -> bool:
        return touches(start, end, corrected_ranges) and not any(
            start < taken_end and end > taken_start for taken_start, taken_end in taken
        )

    return keep


class TextCorrection:
    """A diff of `old` -> `new` that maps offsets in `old` to offsets in `new`."""

    def __init__(self, old: str, new: str):
        self.old = old
        self.new = new
        self.edits, self.changed_lines = diff_edits(old, new)

    @property
    def is_unchanged(self) -> bool:
        """Whether the two texts are identical."""
        return not self.edits

    def map_position(self, position: int, *, bias: Bias) -> tuple[int, bool]:
        """`(new position, exact)`. A position inside a replaced or deleted stretch has no exact image.

        It is clamped to that stretch's start (`left`) or end (`right`). `bias` also
        decides which side of text inserted exactly at `position` the result falls on.
        """
        delta = 0
        for edit in self.edits:
            if position < edit.old_start:
                break
            if position == edit.old_start == edit.old_end:
                return (edit.new_start if bias == "left" else edit.new_end), True
            if position == edit.old_start:
                return edit.new_start, True
            if position < edit.old_end:
                return (edit.new_start if bias == "left" else edit.new_end), False
            if position == edit.old_end:
                return edit.new_end, True
            delta = edit.new_end - edit.old_end
        return position + delta, True

    def _edited_inside(self, start: int, end: int) -> bool:
        return any(
            start < edit.old_start < end
            if edit.old_start == edit.old_end
            else edit.old_start < end and edit.old_end > start
            for edit in self.edits
        )

    def _trimmed(self, start: int, end: int) -> tuple[int, int] | None:
        text = self.new[start:end]
        stripped = text.strip()
        if not stripped:
            return None
        start += len(text) - len(text.lstrip())
        return start, start + len(stripped)

    def _grown(self, start: int, end: int, new_start: int, new_end: int) -> tuple[int, int]:
        """Widen a span over letters typed onto its edges, so `Tangradi, M` + `ark` is one word again."""
        floor, ceiling = self.map_position(start, bias="left")[0], self.map_position(end, bias="right")[0]
        while new_start > floor and self.new[new_start - 1].isalnum() and self.new[new_start].isalnum():
            new_start -= 1
        while new_end < ceiling and self.new[new_end].isalnum() and self.new[new_end - 1].isalnum():
            new_end += 1
        return new_start, new_end

    def remap_span(self, start: int, end: int) -> SpanMove:
        """Carry `old[start:end]` into `new`.

        Text inserted right at either end stays outside the span, unless it carries on
        the word at that end. When an end falls inside an edit, the span's old text is
        looked for again, but only within the lines that were rewritten around it (the
        nearest occurrence wins), never elsewhere in the text.
        """
        new_start, start_exact = self.map_position(start, bias="right")
        new_end, end_exact = self.map_position(end, bias="left")
        if start_exact and end_exact and new_start < new_end:
            grown = self._grown(start, end, new_start, new_end)
            if not self._edited_inside(start, end) and grown == (new_start, new_end):
                if self.new[new_start:new_end] == self.old[start:end]:
                    return SpanMove(fate=SpanFate.MOVED, start=new_start, end=new_end)
            elif trimmed := self._trimmed(*grown):
                return SpanMove(fate=SpanFate.EDITED, start=trimmed[0], end=trimmed[1])
        return self._relocate(start, end)

    def _relocate(self, start: int, end: int) -> SpanMove:
        surface = self.old[start:end]
        rewritten = [lines for lines in self.changed_lines if lines.old_start <= end and lines.old_end >= start]
        if not rewritten:
            return SpanMove(fate=SpanFate.LOST)
        low, high = rewritten[0].new_start, rewritten[-1].new_end
        anchor, _ = self.map_position(start, bias="right")
        found = []
        position = self.new.find(surface, low)
        while position != -1 and position + len(surface) <= high:
            found.append(position)
            position = self.new.find(surface, position + 1)
        if not surface or not found:
            return SpanMove(fate=SpanFate.LOST)
        best = min(found, key=lambda candidate: abs(candidate - anchor))
        return SpanMove(fate=SpanFate.RELOCATED, start=best, end=best + len(surface))

    def remap_range(self, start: int, end: int) -> tuple[int, int]:
        """Carry a range so it covers everything it covered before, plus anything inserted at its edges."""
        return self.map_position(start, bias="left")[0], self.map_position(end, bias="right")[0]

    def changed_ranges(self, previous: list[tuple[int, int]] | None = None) -> list[tuple[int, int]]:
        """Stretches of `new` a person wrote (this edit, plus `previous` ones carried forward), merged."""
        carried = [self.remap_range(start, end) for start, end in previous or []]
        return merge_ranges([*carried, *((edit.new_start, edit.new_end) for edit in self.edits)])


class TextCorrectionRequest(BaseModel):
    """A file's corrected text, replacing its extracted text on every copy of the same content."""

    content: str = Field(min_length=1)
    rerun: list[EnrichmentType] = Field(
        default=[], description="Steps that already read the old text to redo on the new one (default: none)"
    )
    dry_run: bool = Field(default=False, description="Only report what the correction would do")


class CorrectedMention(BaseModel):
    """A mention the correction renames or cannot place."""

    mention_id: str
    label: str = Field(description="Entity or selector type")
    surface_text: str
    new_surface_text: str | None = Field(default=None, description="Its text after the correction, if it survives")


class TextCorrectionSummary(BaseModel):
    """What a correction did (or, on a dry run, would do) across every copy of the file's content."""

    file_count: int = Field(description="Files whose text changes (copies of the same content)")
    kept_count: int = Field(description="Mentions on untouched text, moved to their new offsets")
    renamed: list[CorrectedMention] = Field(default=[], description="Mentions whose text was corrected")
    lost: list[CorrectedMention] = Field(default=[], description="Mentions whose text is gone; deleted")
    corrected_ranges: list[tuple[int, int]] = Field(default=[], description="Stretches of the new text a person wrote")
    chunk_count: int = Field(default=0, description="Search chunks moved onto (or rebuilt from) the corrected text")
    rerunnable: list[EnrichmentType] = Field(
        default=[], description="Steps that already read the old text and can be redone on the new one"
    )
    rerun: list[EnrichmentType] = Field(default=[], description="Steps redone or put back to pending")
    running: list[EnrichmentType] = Field(default=[], description="Steps running on these files now; block saving")
    is_saved: bool = Field(default=False, description="The correction was written")
