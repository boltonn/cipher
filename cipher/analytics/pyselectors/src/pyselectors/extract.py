"""Find, normalize, validate, score, and resolve selectors in a block of text.

Five stages: pattern match -> normalize -> validate (+ attributes) -> context
score -> overlap resolution. All matchers report character offsets into the
exact input string, so a caller can store them directly as
``mention.start_offset`` / ``end_offset`` against ``ExtractedText.content``.

The public entrypoint is a pure, synchronous function. Everything it touches is
precompiled and cached on first use.
"""

import pyselectors.normalize as normalize
import pyselectors.patterns as patterns
import pyselectors.resolve as _resolve
import pyselectors.validate as validate
from cipher.schemas.graph.ontology import SelectorSubtype, SelectorType
from cipher.schemas.graph.spans import SelectorSpan
from pyselectors.attributes import coerce
from pyselectors.context import ContextScorer
from pyselectors.packs.loader import load_pack
from pyselectors.packs.registry import ENABLED_TYPES


def extract_selectors(
    text: str,
    *,
    language: str | None = None,
    region: str | None = None,
    types: set[SelectorType] | None = None,
    min_confidence: float = 0.0,
) -> list[SelectorSpan]:
    """Extract normalized, validated, context-scored selectors from ``text``.

    Args:
        text: The text to scan.
        language: ISO-639-1 hint. Picks the context lexicon and a default phone region.
        region: Explicit ISO-3166 alpha-2 region (wins over ``language``).
        types: Restrict to these selector types (default: every enabled type).
        min_confidence: Drop spans scoring below this.

    Returns:
        Non-overlapping ``SelectorSpan``s sorted by start offset.
    """
    if not text:
        return []

    folded = normalize.fold_digits(text)
    country = normalize.region_for(language=language, region=region)
    wanted = tuple(types) if types else ENABLED_TYPES
    scorer = ContextScorer.for_language(language)

    spans: list[SelectorSpan] = []
    for match in patterns.find_all(folded, types=wanted, country=country):
        pack = _pack_for(match.selector_type, country)
        normalized = normalize.canonicalize(
            pack.normalizer,
            folded[match.start : match.end],
            country=country,
            subtype=match.selector_subtype,
        )
        if not normalized:
            continue

        try:
            attrs = validate.run(match.selector_type, normalized, country=country)
        except validate.SelectorRejected:
            continue

        base = match.base_confidence if match.base_confidence is not None else pack.base_confidence
        confidence = scorer.score(match.selector_type, folded, match.start, match.end, base)
        if match.requires_context and confidence <= base:
            continue
        if confidence < min_confidence:
            continue

        merged = {**match.hint, **attrs}
        spans.append(
            SelectorSpan(
                selector_type=match.selector_type,
                selector_subtype=match.selector_subtype,
                raw_value=text[match.start : match.end],
                normalized_value=normalized,
                start_offset=match.start,
                end_offset=match.end,
                confidence=round(confidence, 4),
                region_hint=merged.get("region") or country,
                attributes=coerce(match.selector_type, merged),
            )
        )

    return _resolve.resolve(spans)


def resolve_selector(
    value: str,
    *,
    selector_type: SelectorType | None = None,
    selector_subtype: SelectorSubtype | None = None,
    language: str | None = None,
    region: str | None = None,
) -> list[SelectorSpan]:
    """Normalize + validate + attribute-extract a bare selector value, retroactively.

    Runs the same three stages (normalize / validate / attributes) as the text
    pass, but over a single value with no surrounding context -- for an analyst
    who pastes a raw selector, or a backfill over stored rows.

    Args:
        value: The raw selector string (the whole string is the candidate).
        selector_type: Force this type (analyst assertion). If omitted, the type
            is inferred by running every enabled pattern set against ``value``.
        selector_subtype: Optional specific provider/network when ``selector_type``
            is forced.
        language: ISO-639-1 hint for the default phone region / country validators.
        region: Explicit ISO-3166 alpha-2 region (wins over ``language``).

    Returns:
        ``[SelectorSpan]`` (offsets span the whole value) when it normalizes and
        validates, else ``[]``. Inference may return more than one candidate.
    """
    text = value.strip()
    if not text:
        return []

    country = normalize.region_for(language=language, region=region)

    if selector_type is None:
        return extract_selectors(text, language=language, region=region)

    normalized, attrs = normalize.normalize_selector(selector_type, text, country)
    if not normalized:
        return []
    return [
        SelectorSpan(
            selector_type=selector_type,
            selector_subtype=selector_subtype,
            raw_value=value,
            normalized_value=normalized,
            start_offset=0,
            end_offset=len(value),
            confidence=1.0,
            region_hint=attrs.get("region") or country,
            attributes=coerce(selector_type, attrs),
        )
    ]


def _pack_for(selector_type: SelectorType, country: str | None):
    try:
        return load_pack(selector_type.value, country)
    except FileNotFoundError:  # pragma: no cover - guarded by registry
        raise
