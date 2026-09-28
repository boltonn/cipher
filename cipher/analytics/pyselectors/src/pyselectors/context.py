"""Stage 2 -- adjust a match's confidence from the words around it.

Weighted lexicon, saturating combination:

    conf = base
    for w in positive weights: conf += w * (max_conf - conf)   # diminishing gains
    for w in negative weights: conf -= |w| * conf              # multiplicative decay
    conf = clamp(conf, 0, max_conf)

With no context cue, ``conf == base``. Each ``ContextScorer`` is cached per
language and holds one precompiled alternation per (type, sign), so scoring a
match is a handful of ``search`` calls over a <=60-char window.
"""

import functools

import regex

from cipher.schemas.graph.ontology import SelectorType
from pyselectors.packs.loader import load_pack
from pyselectors.packs.registry import ENABLED_TYPES

_SENTINEL = "\x00"
_FALLBACK_LANG = "en"


def _compile_terms(terms) -> tuple[list[tuple[object, float]], list[tuple[object, float]]]:
    positive: list[tuple[object, float]] = []
    negative: list[tuple[object, float]] = []
    for t in terms:
        pat = t.pattern if t.pattern is not None else regex.escape(t.term)
        compiled = regex.compile(pat, regex.VERSION1 | regex.IGNORECASE)
        (positive if t.weight >= 0 else negative).append((compiled, abs(t.weight)))
    return positive, negative


class ContextScorer:
    """Per-language scorer over every enabled selector type."""

    __slots__ = ("_lang", "_by_type")

    def __init__(self, lang: str | None):
        from pyselectors.normalize import region_for

        self._lang = (lang or "").lower()[:2]
        country = region_for(language=self._lang or None, region=None)
        self._by_type: dict[SelectorType, dict] = {}
        for selector_type in ENABLED_TYPES:
            try:
                pack = load_pack(selector_type.value, country)
            except FileNotFoundError:
                continue
            langs = {self._lang, _FALLBACK_LANG} if self._lang else {_FALLBACK_LANG}
            terms = [term for lang in langs for term in pack.context.terms.get(lang, [])]
            pos, neg = _compile_terms(terms)
            self._by_type[selector_type] = {
                "before": pack.context.window_before,
                "after": pack.context.window_after,
                "max": pack.max_confidence,
                "pos": pos,
                "neg": neg,
            }

    @classmethod
    @functools.lru_cache(maxsize=32)
    def for_language(cls, lang: str | None) -> "ContextScorer":
        """Return the cached scorer for ``lang`` (built once per language)."""
        return cls(lang)

    def score(self, selector_type: SelectorType, text: str, start: int, end: int, base: float) -> float:
        """Adjust ``base`` by the context cues within the pack's window around ``[start, end)``."""
        cfg = self._by_type.get(selector_type)
        if cfg is None:
            return base
        max_conf = cfg["max"]
        left = text[max(0, start - cfg["before"]) : start]
        right = text[end : end + cfg["after"]]
        haystack = f"{left}{_SENTINEL}{right}"
        conf = min(base, max_conf)
        for compiled, weight in cfg["pos"]:
            if compiled.search(haystack):
                conf += weight * (max_conf - conf)
        for compiled, weight in cfg["neg"]:
            if compiled.search(haystack):
                conf -= weight * conf
        return max(0.0, min(max_conf, conf))
