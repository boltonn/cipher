"""Find, normalize, validate, score, and resolve selectors in a block of text.

Five stages: pattern match -> normalize -> validate (+ attributes) -> context
score -> overlap resolution. All matchers report character offsets into the
exact input string, so a caller can store them directly as
``mention.start_offset`` / ``end_offset`` against ``ExtractedText.content``.

The public entrypoint is a pure, synchronous function. Everything it touches is
precompiled and cached on first use.
"""

from importlib.resources import files

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

_PACK_DIR = files("pyselectors.packs.data")


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
        language: ISO-639-1 hint. Picks the context lexicon and country pattern overlays.
        region: Explicit ISO-3166 alpha-2 region (wins over ``language``). A phone without
            its own country code is parsed in it only when given; otherwise it stays national.
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
        # a phone's country comes from the number or an explicit region, never from the language
        value_country = _value_country(match.selector_type, country=country, region=region)
        normalized = normalize.canonicalize(
            pack.normalizer,
            folded[match.start : match.end],
            country=value_country,
            subtype=match.selector_subtype,
        )
        if not normalized:
            continue

        try:
            attrs = validate.run(match.selector_type, normalized, country=value_country)
        except validate.SelectorRejected:
            continue

        base = match.base_confidence if match.base_confidence is not None else pack.base_confidence
        confidence = scorer.score(match.selector_type, folded, match.start, match.end, base)
        # a number with no country of its own is unchecked digits: only a phone cue (`Tel:`) makes it one
        needs_context = match.requires_context or (
            match.selector_type is SelectorType.PHONE and normalize.is_national_phone(normalized)
        )
        if needs_context and confidence <= base:
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
                region_hint=merged.get("region") or value_country,
                attributes=coerce(match.selector_type, merged),
            )
        )

    return _resolve.resolve(spans)


def _value_country(selector_type: SelectorType, *, country: str | None, region: str | None) -> str | None:
    """The region a value is parsed in: phones only take an explicit `region`, other types the overlay country."""
    if selector_type is SelectorType.PHONE:
        return region.upper() if region else None
    return country


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
        language: ISO-639-1 hint for country validators (never a phone's country).
        region: Explicit ISO-3166 alpha-2 region (wins over ``language``); the only way an
            unprefixed phone gets a country.

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

    country = _value_country(selector_type, country=country, region=region)
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


def overlay_countries(selector_type: SelectorType) -> tuple[str, ...]:
    """Regions with a country overlay for `selector_type` (e.g. national_id: `CN`, `IR`, `RU`)."""
    prefix = f"{selector_type.value}."
    return tuple(
        sorted(p.name[len(prefix) : -len(".json")].upper() for p in _PACK_DIR.iterdir() if p.name.startswith(prefix))
    )


def resolve_cell(
    value: str,
    selector_type: SelectorType,
    *,
    region: str | None = None,
    language: str | None = None,
) -> SelectorSpan | None:
    """Validate one table cell as `selector_type`, or None.

    Stricter than `resolve_selector(selector_type=...)`, which trusts the caller's
    type and only normalizes. Here one of the type's own patterns has to match the
    whole cell before normalize + validate run. Patterns that normally need context
    words (a bare `@handle`, an unformatted phone) count, because the column is the
    context. Without a region, types with country overlays (national ids) try each.
    """
    text = value.strip()
    if not text:
        return None
    folded = normalize.fold_digits(text)
    country = normalize.region_for(language=language, region=region)
    countries = (country,) if country or not overlay_countries(selector_type) else overlay_countries(selector_type)
    for candidate in countries:
        pack = _pack_for(selector_type, candidate)
        value_country = _value_country(selector_type, country=candidate, region=region)
        for match in patterns.find_all(folded, types=(selector_type,), country=candidate):
            if match.start != 0 or match.end != len(folded):
                continue
            normalized = normalize.canonicalize(
                pack.normalizer, folded, country=value_country, subtype=match.selector_subtype
            )
            if not normalized:
                continue
            try:
                attrs = validate.run(selector_type, normalized, country=value_country)
            except validate.SelectorRejected:
                continue
            merged = {**match.hint, **attrs}
            return SelectorSpan(
                selector_type=selector_type,
                selector_subtype=match.selector_subtype or _subtype(merged.get("subtype")),
                raw_value=text,
                normalized_value=normalized,
                start_offset=0,
                end_offset=len(text),
                confidence=match.base_confidence if match.base_confidence is not None else pack.base_confidence,
                region_hint=merged.get("region") or value_country,
                attributes=coerce(selector_type, merged),
            )
    return None


def _subtype(value: str | None) -> SelectorSubtype | None:
    try:
        return SelectorSubtype(value) if value else None
    except ValueError:
        return None


def _pack_for(selector_type: SelectorType, country: str | None):
    try:
        return load_pack(selector_type.value, country)
    except FileNotFoundError:  # pragma: no cover - guarded by registry
        raise
