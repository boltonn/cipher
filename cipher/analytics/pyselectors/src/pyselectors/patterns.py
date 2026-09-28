"""Stage 1 -- find candidate spans with precompiled per-type regexes.

One compiled list per (type, country), cached for the life of the process. A
scan is ``len(ENABLED_TYPES)`` calls to ``regex.finditer`` over the whole text.
"""

import functools
from dataclasses import dataclass, field

import regex

from cipher.schemas.graph.ontology import SelectorSubtype, SelectorType
from pyselectors.packs.loader import load_pack
from pyselectors.packs.registry import ENABLED_TYPES


@dataclass(frozen=True, slots=True)
class RawMatch:
    selector_type: SelectorType
    start: int
    end: int
    selector_subtype: SelectorSubtype | None = None
    hint: dict[str, str] = field(default_factory=dict)
    base_confidence: float | None = None
    requires_context: bool = False


@functools.cache
def _compiled(selector_type: str, country: str | None):
    pack = load_pack(selector_type, country)
    specs = list(pack.patterns)
    if country and country in pack.countries:
        specs += list(pack.countries[country].patterns)
    return tuple((regex.compile(spec.regex, regex.VERSION1 | regex.MULTILINE), spec) for spec in specs)


def find_all(
    text: str,
    *,
    types: tuple[SelectorType, ...] | None = None,
    country: str | None = None,
) -> list[RawMatch]:
    """Every candidate span in ``text``, sorted by (start, longest-first)."""
    out: list[RawMatch] = []
    for selector_type in types or ENABLED_TYPES:
        for compiled, spec in _compiled(selector_type.value, country):
            for m in compiled.finditer(text):
                if m.start() == m.end():
                    continue
                out.append(
                    RawMatch(
                        selector_type=selector_type,
                        start=m.start(),
                        end=m.end(),
                        selector_subtype=spec.subtype,
                        hint=dict(spec.hint),
                        base_confidence=spec.base_confidence,
                        requires_context=spec.requires_context,
                    )
                )
    out.sort(key=lambda r: (r.start, -(r.end - r.start)))
    return out
