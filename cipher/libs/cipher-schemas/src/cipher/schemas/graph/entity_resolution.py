"""Entity-resolution contracts: candidate, feature, explanation, and the scorer config.

`ResolutionCandidate` is what the candidate-generation primitive
(`PostgresEntityRepository.get_resolution_candidates`) returns. The Fellegi-Sunter
scorer (`cipher.orchestration.entity_resolution`) grades each candidate into a
`ResolutionFeature` list, a `score`, a `ResolutionBand`, and a
`ResolutionExplanation` -- the last is stored verbatim on `entity_match` and
rendered as the review-queue "why".
"""

from pydantic import Field

from cipher.schemas._base.base import BaseModel, EnumStr, StrEnum
from cipher.schemas.graph.entity import EntitySummary


class FeatureLevel(StrEnum):
    """Ordinal outcome of one comparison feature. `CONFLICT` is a hard veto."""

    CONFLICT = "conflict"
    NONE = "none"
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    EXACT = "exact"


class ResolutionBand(StrEnum):
    """What the decision policy does with a scored candidate."""

    AUTO = "auto"
    REVIEW = "review"
    PROVISIONAL = "provisional"


class ResolutionFeature(BaseModel):
    """One scored comparison signal between a mention and a candidate."""

    name: EnumStr = Field(description="Feature id, e.g. 'name_structure', 'selector_overlap'")
    level: FeatureLevel
    weight: float = Field(description="Fellegi-Sunter match weight for this level (log2 m/u)")
    contribution: float = Field(description="Signed contribution to the total log-odds")
    detail: str | None = Field(default=None, description="Human-readable evidence")


class ResolutionExplanation(BaseModel):
    """The full 'why' for one mention->entity decision. Stored on `entity_match.explanation`."""

    score: float = Field(ge=0, le=1)
    band: ResolutionBand
    auto_rule: str | None = Field(default=None, description="Which always-auto rule fired, when band == auto")
    blocking: list[EnumStr] = Field(default_factory=list, description="Strategies that surfaced the candidate")
    candidates_considered: int = 0
    runner_up_score: float | None = Field(default=None, ge=0, le=1)
    features: list[ResolutionFeature] = Field(default_factory=list)


class EntityMatchRef(BaseModel):
    """A candidate row from `entity_match`, flattened for the resolution view."""

    id: str
    entity_id: str
    status: EnumStr
    similarity_score: float
    match_method: EnumStr
    explanation: ResolutionExplanation | None = None


class MentionResolution(BaseModel):
    """The 'why did/didn't this resolve?' view for one mention (its name group)."""

    mention_id: str
    normalized_value: str | None = None
    resolved_entity_id: str | None = Field(
        default=None, description="Set once the mention (or its group) has been attached"
    )
    resolved_by: str | None = Field(default=None, description="'system' | 'analyst' | None")
    candidates: list[EntityMatchRef] = Field(
        default_factory=list, description="Group-level entity_match rows, best score first"
    )


class ResolutionCandidate(BaseModel):
    """A possible canonical entity for an unresolved mention."""

    entity: EntitySummary
    blocked_by: list[str] = Field(
        default_factory=list,
        description="Strategies that surfaced this candidate: 'selector' | 'name_exact' | 'key:<key_type>' | 'trigram'",
    )
    trigram_score: float | None = Field(
        default=None, ge=0, le=1, description="Name trigram similarity, when trigram blocking hit"
    )
    # Filled by the scorer; empty from bare blocking.
    features: list[ResolutionFeature] = Field(default_factory=list)
    score: float | None = Field(default=None, ge=0, le=1)
    band: ResolutionBand | None = None
    explanation: str | None = Field(default=None, description="One-line reason for logs / match_reason")


# --- scorer configuration -----------------------------------------------------
#
# Fellegi-Sunter match weights: for feature F at level L, weight = log2(m/u) where
# m = P(L | same entity), u = P(L | different). Positive weight = evidence for a
# match. Hand-set and conservative below; `scripts/calibrate_resolution.py` (R5)
# re-estimates them from `entity_match` review history. `u` for name features is
# term-frequency-adjusted at runtime (a match on a rare name counts for more).

_DEFAULT_WEIGHTS: dict[str, dict[str, float]] = {
    # A shared address/phone is strong identity evidence but not certain (shared
    # family mailboxes, role accounts) -- keep it below the level where it alone
    # saturates the score, so a name signal still moves the ranking.
    "selector_overlap": {"exact": 6.0, "none": 0.0},
    # An email address that spells the name (`nbolton04@` / Nick Bolton) -- or spells someone
    # else's (`cbolton@` / Nick Bolton). Soft both ways: family mailboxes are shared.
    "address_name": {"strong": 2.0, "none": 0.0, "weak": -1.5},
    "type_agreement": {"exact": 0.5, "none": 0.0, "conflict": -30.0},
    "name_exact": {"exact": 4.5, "none": 0.0},
    "name_translit": {"exact": 3.5, "none": 0.0},
    "name_phonetic": {"exact": 1.5, "none": 0.0},
    "name_trigram": {"strong": 2.5, "moderate": 1.0, "weak": 0.2, "none": 0.0},
    "name_structure": {
        "exact": 4.0,
        "strong": 2.6,
        "moderate": 1.2,
        "weak": -0.5,
        "none": 0.0,
        "conflict": -30.0,
    },
    "attribute_agreement": {
        "strong": 2.5,
        "moderate": 1.0,
        "none": 0.0,
        "conflict": -8.0,
    },
    "co_mention_prior": {"strong": 1.2, "moderate": 0.5, "none": 0.0},
}

# Base log-odds by mention provenance -- a structured header/contact field is a
# higher-trust starting point than free-text prose.
_DEFAULT_BASE_PRIOR: dict[str, float] = {
    "email_header": -2.0,
    "metadata": -2.5,
    "pattern": -3.0,
    "text": -3.5,
    "image": -3.5,
}


class EntityResolutionConfig(BaseModel):
    """Knobs for the resolution sweep. Defaults are conservative (auto precision first)."""

    auto_threshold: float = Field(default=0.92, ge=0, le=1)
    review_low: float = Field(default=0.55, ge=0, le=1)
    min_margin: float = Field(default=0.15, ge=0, le=1, description="Required gap between #1 and #2 to auto-resolve")
    auto_methods: list[str] = Field(
        default_factory=lambda: ["selector"],
        description="Blocking tags eligible for auto-resolve at all",
    )
    create_provisional: bool = True
    no_name_evidence_cap: float = Field(
        default=0.6,
        ge=0,
        le=1,
        description="Score ceiling for a candidate with no name evidence at all (only a shared "
        "address, co-mention, ...) -- 'friend <nbolton04@...>' stays a suggestion, not a near-certain one.",
    )
    require_name_agreement_for_auto: bool = Field(
        default=True,
        description="A selector-backed auto also needs a real name match (any name_* exact, or "
        "name_structure/name_trigram strong+). Blocks a bare same-surname match on a shared "
        "family mailbox from auto-resolving.",
    )
    min_mentions: int = Field(default=2, ge=1)
    cross_dataset: bool = False
    use_embeddings: bool = False
    per_key_cap: int = Field(default=200, ge=1)
    candidate_limit: int = Field(default=50, ge=1, le=200)
    base_prior: dict[str, float] = Field(default_factory=lambda: dict(_DEFAULT_BASE_PRIOR))
    weights: dict[str, dict[str, float]] = Field(
        default_factory=lambda: {k: dict(v) for k, v in _DEFAULT_WEIGHTS.items()}
    )


DEFAULT_RESOLUTION_CONFIG = EntityResolutionConfig()
