"""Resolve a model's surface strings to character spans in the analyzed text.

An LLM returns the text of a mention, not its position. Each surface form is
matched to its first not-yet-claimed occurrence in the source (exact first,
then case-insensitive), so repeated mentions of the same string map to distinct
spans and a hallucinated string that never appears is dropped by the caller.
"""

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
