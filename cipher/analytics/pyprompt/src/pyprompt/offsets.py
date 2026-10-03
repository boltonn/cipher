"""Resolve a model's surface strings to character spans in the analyzed text.

An LLM returns the text of a mention, not its position. Each surface form is
matched to its first not-yet-claimed occurrence in the source (exact first,
then case-insensitive), so repeated mentions of the same string map to distinct
spans and a hallucinated string that never appears is dropped by the caller.
"""

import re
from bisect import bisect_right


class OffsetResolver:
    """Claims successive occurrences of surface strings in one source text."""

    def __init__(self, source: str):
        self._source = source
        self._lower = source.lower()
        self._claimed: list[tuple[int, int]] = []

    def locate(self, surface_text: str) -> tuple[int, int] | None:
        """Return the (start, end) of the next unclaimed occurrence, or None."""
        needle = surface_text.strip()
        if not needle:
            return None
        span = self._find(self._source, needle) or self._find(self._lower, needle.lower())
        if span is not None:
            self._claim(span)
        return span

    def _find(self, haystack: str, needle: str) -> tuple[int, int] | None:
        start = haystack.find(needle)
        while start != -1:
            end = start + len(needle)
            if not self._overlaps(start, end):
                return start, end
            start = haystack.find(needle, start + 1)
        return None

    def _overlaps(self, start: int, end: int) -> bool:
        idx = bisect_right([s for s, _ in self._claimed], start)
        return any(start < e and s < end for s, e in self._claimed[max(0, idx - 1) : idx + 1])

    def _claim(self, span: tuple[int, int]) -> None:
        self._claimed.append(span)
        self._claimed.sort()


_WORD = re.compile(r"\w+|[^\w\s]")
_MIN_STEM = 3


def _same_stem(a: str, b: str) -> bool:
    """Two word forms that differ only in their ending (`клуб` / `клубе`, `Verein` / `Vereins`)."""
    a, b = a.casefold(), b.casefold()
    if a == b:
        return True
    common = len(a) if b.startswith(a) else len(b) if a.startswith(b) else 0
    if not common:
        common = next((i for i, (x, y) in enumerate(zip(a, b, strict=False)) if x != y), min(len(a), len(b)))
    return common >= _MIN_STEM and common >= max(len(a), len(b)) - 2


def find_span(source: str, value: str | None) -> tuple[int, int] | None:
    """Where `value` occurs in `source`: exact, case-insensitive, then allowing inflected word endings.

    A model asked to copy text verbatim still writes the dictionary form in inflected languages
    (`яхт-клуб «Нева»` for `яхт-клубе «Нева»`). The last step matches the same words in order,
    each differing only in its last couple of letters, and returns the span as the source writes it.
    """
    value = (value or "").strip()
    if not value:
        return None
    index = source.find(value)
    if index < 0:
        index = source.casefold().find(value.casefold())
    if index >= 0:
        return index, index + len(value)
    wanted = _WORD.findall(value)
    words = list(_WORD.finditer(source))
    for start in range(len(words) - len(wanted) + 1):
        if all(_same_stem(w, words[start + i].group()) for i, w in enumerate(wanted)):
            return words[start].start(), words[start + len(wanted) - 1].end()
    return None
