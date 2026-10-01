"""Fellegi-Sunter scorer for entity resolution.

Pure functions. Given a mention and a blocked candidate (plus the pre-fetched
selectors / attributes / neighbours each side needs), `score_candidate` produces
a `ResolutionFeature` list whose match weights sum -- with a provenance-based
prior -- to a log-odds, then a `[0, 1]` score. `decide` bands the ranked
candidates into auto / review / (nothing -> provisional). `build_explanation`
packages the waterfall stored on `entity_match.explanation`.

The R3 sweep builds the `*ScoringInput`s and persists the result; this module
does no I/O and imports no repository.
"""

from dataclasses import dataclass, field
from math import log2

from cipher.names import Culture, compare_names, fold, phonetic_key, to_latin
from cipher.names.compare import Level
from cipher.schemas.graph.entity_match import EntityMatchMethod
from cipher.schemas.graph.entity_resolution import (
    EntityResolutionConfig,
    FeatureLevel,
    ResolutionBand,
    ResolutionExplanation,
    ResolutionFeature,
)
from cipher.schemas.graph.ontology import EntityType, guess_actor_type

_LEVEL_FROM_COMPARE = {
    Level.CONFLICT: FeatureLevel.CONFLICT,
    Level.NONE: FeatureLevel.NONE,
    Level.WEAK: FeatureLevel.WEAK,
    Level.MODERATE: FeatureLevel.MODERATE,
    Level.STRONG: FeatureLevel.STRONG,
    Level.EXACT: FeatureLevel.EXACT,
}
_NAME_FEATURES = frozenset({"name_exact", "name_translit", "name_phonetic", "name_trigram", "name_structure"})
_METHOD_FROM_FEATURE = {
    "selector_overlap": EntityMatchMethod.SELECTOR_BLOCKING,
    "name_exact": EntityMatchMethod.NAME_EXACT,
    "name_translit": EntityMatchMethod.NAME_TRANSLIT,
    "name_phonetic": EntityMatchMethod.NAME_PHONETIC,
    "name_structure": EntityMatchMethod.NAME_STRUCTURE,
    "name_trigram": EntityMatchMethod.NAME_FUZZY,
}


@dataclass(frozen=True, slots=True)
class MentionScoringInput:
    """Everything the scorer needs about the unresolved mention (or name group)."""

    name: str
    normalized_name: str
    entity_type: EntityType | None
    provenance: str  # 'email_header' | 'metadata' | 'pattern' | 'text' | 'image'
    culture: str | None = None
    selector_values: frozenset[str] = frozenset()
    attributes: dict[str, str] = field(default_factory=dict)  # date_of_birth | nationality | employer
    neighbor_entity_ids: frozenset[str] = frozenset()
    name_df: int = 1  # entities sharing this normalized name in scope (term-frequency)


@dataclass(frozen=True, slots=True)
class CandidateScoringInput:
    """Everything the scorer needs about one blocked candidate entity."""

    entity_id: str
    entity_type: EntityType
    display_name: str
    aliases: tuple[str, ...] = ()
    selector_values: frozenset[str] = frozenset()
    attributes: dict[str, str] = field(default_factory=dict)
    neighbor_entity_ids: frozenset[str] = frozenset()
    trigram_score: float | None = None
    blocked_by: tuple[str, ...] = ()


@dataclass(slots=True)
class ScoredCandidate:
    """A candidate after scoring. `band` is filled by `decide`."""

    entity_id: str
    score: float
    vetoed: bool
    features: list[ResolutionFeature]
    match_method: EntityMatchMethod
    blocked_by: tuple[str, ...]
    band: ResolutionBand | None = None


def _match_weight(config: EntityResolutionConfig, feature: str, level: FeatureLevel) -> float:
    return config.weights.get(feature, {}).get(level.value, 0.0)


def _tf_scale(name_df: int) -> float:
    """Down-weight name evidence for common names. df=1 -> 1.0, df=16 -> ~0.2."""
    return 1.0 / (1.0 + log2(max(1, name_df)))


def _logistic(log_odds: float) -> float:
    log_odds = max(-40.0, min(40.0, log_odds))
    return 1.0 / (1.0 + 2.0 ** (-log_odds))


def _names(candidate: CandidateScoringInput) -> list[str]:
    return [candidate.display_name, *(a for a in candidate.aliases if a and a.strip())]


def _culture(value: str | None) -> Culture | None:
    if not value:
        return None
    try:
        return Culture(value)
    except ValueError:
        return None


# --- individual features -------------------------------------------------------


def _f_type_agreement(m: MentionScoringInput, c: CandidateScoringInput) -> tuple[FeatureLevel, str]:
    mt = m.entity_type or guess_actor_type(m.name)
    if mt is None:
        return FeatureLevel.NONE, "mention type unknown"
    if mt == c.entity_type:
        return FeatureLevel.EXACT, f"both {c.entity_type.value}"
    return FeatureLevel.CONFLICT, f"{mt.value} vs {c.entity_type.value}"


def _f_selector_overlap(m: MentionScoringInput, c: CandidateScoringInput) -> tuple[FeatureLevel, str]:
    shared = m.selector_values & c.selector_values
    if shared:
        return FeatureLevel.EXACT, "shared " + ", ".join(sorted(shared)[:3])
    return FeatureLevel.NONE, ""


def _f_name_exact(m: MentionScoringInput, c: CandidateScoringInput) -> tuple[FeatureLevel, str]:
    mf = fold(m.name)
    for name in _names(c):
        if mf and fold(name) == mf:
            return FeatureLevel.EXACT, f"folds to {mf!r}"
    return FeatureLevel.NONE, ""


def _f_name_translit(m: MentionScoringInput, c: CandidateScoringInput) -> tuple[FeatureLevel, str]:
    ml = fold(to_latin(m.name))
    for name in _names(c):
        if ml and fold(to_latin(name)) == ml:
            return FeatureLevel.EXACT, f"transliterates to {ml!r}"
    return FeatureLevel.NONE, ""


def _f_name_phonetic(m: MentionScoringInput, c: CandidateScoringInput) -> tuple[FeatureLevel, str]:
    mp = phonetic_key(m.name)
    for name in _names(c):
        if mp and phonetic_key(name) == mp:
            return FeatureLevel.EXACT, f"phonetic key {mp!r}"
    return FeatureLevel.NONE, ""


def _f_name_trigram(m: MentionScoringInput, c: CandidateScoringInput) -> tuple[FeatureLevel, str]:
    s = c.trigram_score
    if s is None:
        return FeatureLevel.NONE, ""
    if s >= 0.85:
        return FeatureLevel.STRONG, f"similarity {s:.2f}"
    if s >= 0.55:
        return FeatureLevel.MODERATE, f"similarity {s:.2f}"
    if s >= 0.35:
        return FeatureLevel.WEAK, f"similarity {s:.2f}"
    return FeatureLevel.NONE, f"similarity {s:.2f}"


def _f_name_structure(m: MentionScoringInput, c: CandidateScoringInput) -> tuple[FeatureLevel, str]:
    best = Level.CONFLICT
    detail = ""
    given_conflict = False
    culture = _culture(m.culture)
    for name in _names(c):
        cmp = compare_names(m.name, name, culture=culture)
        if cmp.level > best:
            best, detail = cmp.level, cmp.explanation
        # Two fully-spelled, unrelated first names under the same surname = a
        # different person (a relative, a shared mailbox) -- not a weak match.
        if cmp.components.get("surname") in ("exact", "gendered") and cmp.components.get("given") == "differ":
            given_conflict = True
    if given_conflict and best <= Level.MODERATE:
        return FeatureLevel.CONFLICT, "same surname but a different first name -- likely a different person"
    return _LEVEL_FROM_COMPARE[best], detail


def _f_attribute_agreement(m: MentionScoringInput, c: CandidateScoringInput) -> tuple[FeatureLevel, str]:
    md, cd = m.attributes.get("date_of_birth"), c.attributes.get("date_of_birth")
    if md and cd and md != cd:
        return FeatureLevel.CONFLICT, f"DOB {md} vs {cd}"
    if md and cd and md == cd:
        return FeatureLevel.STRONG, f"DOB {md}"
    for key in ("nationality", "employer"):
        mv, cv = m.attributes.get(key), c.attributes.get(key)
        if mv and cv and fold(mv) == fold(cv):
            return FeatureLevel.MODERATE, f"{key} {mv}"
    return FeatureLevel.NONE, ""


def _f_co_mention_prior(m: MentionScoringInput, c: CandidateScoringInput) -> tuple[FeatureLevel, str]:
    overlap = len(m.neighbor_entity_ids & c.neighbor_entity_ids)
    if overlap >= 2:
        return FeatureLevel.STRONG, f"{overlap} shared neighbours"
    if overlap == 1:
        return FeatureLevel.MODERATE, "1 shared neighbour"
    return FeatureLevel.NONE, ""


_FEATURES = (
    ("type_agreement", _f_type_agreement),
    ("selector_overlap", _f_selector_overlap),
    ("name_exact", _f_name_exact),
    ("name_translit", _f_name_translit),
    ("name_phonetic", _f_name_phonetic),
    ("name_trigram", _f_name_trigram),
    ("name_structure", _f_name_structure),
    ("attribute_agreement", _f_attribute_agreement),
    ("co_mention_prior", _f_co_mention_prior),
)


def score_candidate(
    mention: MentionScoringInput, candidate: CandidateScoringInput, config: EntityResolutionConfig
) -> ScoredCandidate:
    """Grade one candidate. A `conflict` on any feature vetoes it (score 0)."""
    tf = _tf_scale(mention.name_df)
    features: list[ResolutionFeature] = []
    exact_name_hit = False

    for name, fn in _FEATURES:
        level, detail = fn(mention, candidate)
        # Don't pay the translit / phonetic weight when the stronger name_exact
        # already fired -- they're the same evidence.
        if name in ("name_translit", "name_phonetic") and exact_name_hit and level == FeatureLevel.EXACT:
            level = FeatureLevel.NONE
        if name == "name_exact" and level == FeatureLevel.EXACT:
            exact_name_hit = True

        weight = _match_weight(config, name, level)
        contribution = weight * tf if (name in _NAME_FEATURES and weight > 0) else weight
        features.append(
            ResolutionFeature(
                name=name,
                level=level,
                weight=round(weight, 3),
                contribution=round(contribution, 3),
                detail=detail or None,
            )
        )

    vetoed = any(f.level == FeatureLevel.CONFLICT for f in features)
    prior = config.base_prior.get(mention.provenance, -3.5)
    total = prior + sum(f.contribution for f in features)
    score = 0.0 if vetoed else _logistic(total)
    if not vetoed and not any(f.name in _NAME_FEATURES and f.level != FeatureLevel.NONE for f in features):
        score = min(score, config.no_name_evidence_cap)

    positive = [f for f in features if f.contribution > 0]
    method = (
        _METHOD_FROM_FEATURE.get(max(positive, key=lambda f: f.contribution).name, EntityMatchMethod.NAME_FUZZY)
        if positive
        else EntityMatchMethod.NAME_FUZZY
    )
    return ScoredCandidate(
        entity_id=candidate.entity_id,
        score=round(score, 4),
        vetoed=vetoed,
        features=features,
        match_method=method,
        blocked_by=candidate.blocked_by,
    )


_LEVEL_RANK = {
    FeatureLevel.CONFLICT: -1,
    FeatureLevel.NONE: 0,
    FeatureLevel.WEAK: 1,
    FeatureLevel.MODERATE: 2,
    FeatureLevel.STRONG: 3,
    FeatureLevel.EXACT: 4,
}


def _name_agrees(by_name: dict[str, FeatureLevel]) -> bool:
    """A real name match: any name_* at EXACT, or name_structure/name_trigram at STRONG+.

    A bare `name_structure:moderate` -- "surname exact, given differs (same family?)" -- does
    not count, so a shared family mailbox can't auto-resolve one relative onto another.
    """
    if any(by_name.get(f) == FeatureLevel.EXACT for f in ("name_exact", "name_translit", "name_phonetic")):
        return True
    return (
        _LEVEL_RANK.get(by_name.get("name_structure", FeatureLevel.NONE), 0) >= 3
        or _LEVEL_RANK.get(by_name.get("name_trigram", FeatureLevel.NONE), 0) >= 3
    )


def _auto_eligible(sc: ScoredCandidate, config: EntityResolutionConfig) -> str | None:
    """Return the auto-rule name if this candidate may auto-resolve, else None."""
    if sc.vetoed or not (set(sc.blocked_by) & set(config.auto_methods)):
        return None
    by_name = {f.name: f.level for f in sc.features}
    if (
        "selector" in sc.blocked_by
        and by_name.get("selector_overlap") == FeatureLevel.EXACT
        and by_name.get("type_agreement") != FeatureLevel.CONFLICT
        and (not config.require_name_agreement_for_auto or _name_agrees(by_name))
    ):
        return "exact selector on structured field"
    return None


def decide(scored: list[ScoredCandidate], config: EntityResolutionConfig) -> list[ScoredCandidate]:
    """Band the ranked candidates in place. Empty / all-vetoed -> nothing auto or review."""
    live = sorted((s for s in scored if not s.vetoed), key=lambda s: s.score, reverse=True)
    for i, sc in enumerate(live):
        runner_up = live[i + 1].score if i + 1 < len(live) else 0.0
        if (
            i == 0
            and sc.score >= config.auto_threshold
            and (sc.score - runner_up) >= config.min_margin
            and _auto_eligible(sc, config)
        ):
            sc.band = ResolutionBand.AUTO
        elif sc.score >= config.review_low:
            sc.band = ResolutionBand.REVIEW
        else:
            sc.band = None
    return scored


def dominant_method(sc: ScoredCandidate) -> EntityMatchMethod:
    """The match method to stamp on the `entity_match` row."""
    return sc.match_method


def build_explanation(
    sc: ScoredCandidate,
    *,
    candidates_considered: int,
    runner_up_score: float | None,
    config: EntityResolutionConfig,
) -> ResolutionExplanation:
    """Package one scored candidate's waterfall for `entity_match.explanation`."""
    band = sc.band or ResolutionBand.PROVISIONAL
    return ResolutionExplanation(
        score=sc.score,
        band=band,
        auto_rule=_auto_eligible(sc, config) if band == ResolutionBand.AUTO else None,
        blocking=list(sc.blocked_by),
        candidates_considered=candidates_considered,
        runner_up_score=runner_up_score,
        features=[f for f in sc.features if f.level != FeatureLevel.NONE],
    )
