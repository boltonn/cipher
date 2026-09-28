"""Stage 5 -- drop overlapping spans, keeping the strongest.

On an overlap the winner is decided by, in order: pack priority, confidence,
then span length. A specific subtype outranks an umbrella of the same type
(handled by giving the umbrella a lower effective priority when it has no
subtype but the rival does).
"""

from cipher.schemas.graph.spans import SelectorSpan
from pyselectors.packs.registry import priority


def _rank(span: SelectorSpan) -> tuple[int, float, int]:
    prio = priority(span.selector_type)
    if span.selector_subtype is not None:
        prio += 1
    return (prio, span.confidence, span.end_offset - span.start_offset)


def resolve(spans: list[SelectorSpan]) -> list[SelectorSpan]:
    """Return a non-overlapping subset, strongest span per region, sorted by offset."""
    ordered = sorted(spans, key=lambda s: (s.start_offset, -(s.end_offset - s.start_offset)))
    kept: list[SelectorSpan] = []
    for span in ordered:
        clash_idx = next(
            (i for i, k in enumerate(kept) if span.start_offset < k.end_offset and k.start_offset < span.end_offset),
            None,
        )
        if clash_idx is None:
            kept.append(span)
        elif _rank(span) > _rank(kept[clash_idx]):
            kept[clash_idx] = span
    return sorted(kept, key=lambda s: (s.start_offset, s.end_offset))
