"""Validated shape of a selector config pack (one JSON file per selector type).

A pack is pure data: the regex patterns that find a candidate, the base
confidence a bare match earns, the per-language context lexicon that adjusts it,
and the names of the normalizer / validator to run. Packs are loaded once and
cached; nothing here touches I/O.
"""

from pydantic import BaseModel, Field, model_validator

from cipher.schemas.graph.ontology import SelectorSubtype, SelectorType

_CONTEXT_LANGS = frozenset({"en", "ru", "uk", "zh", "ar", "fa", "es", "fr"})


class ContextTerm(BaseModel):
    """One weighted context cue. Either a literal ``term`` or a ``pattern`` regex."""

    term: str | None = None
    pattern: str | None = None
    weight: float = Field(ge=-1.0, le=1.0, description="Positive lifts confidence, negative penalises")

    @model_validator(mode="after")
    def _one_of(self) -> "ContextTerm":
        if (self.term is None) == (self.pattern is None):
            raise ValueError("ContextTerm needs exactly one of `term` or `pattern`")
        return self


class ContextConfig(BaseModel):
    """Per-direction window sizes (chars) and the per-language weighted lexicon."""

    window_before: int = Field(default=40, ge=0, le=400)
    window_after: int = Field(default=20, ge=0, le=400)
    terms: dict[str, list[ContextTerm]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _known_langs(self) -> "ContextConfig":
        unknown = set(self.terms) - _CONTEXT_LANGS
        if unknown:
            raise ValueError(f"unknown context languages: {sorted(unknown)}")
        return self


class PatternSpec(BaseModel):
    """One regex that yields a candidate span, plus the subtype/attributes it implies."""

    name: str | None = None
    regex: str
    subtype: SelectorSubtype | None = None
    hint: dict[str, str] = Field(default_factory=dict)
    base_confidence: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="Overrides the pack base for this pattern (e.g. an unambiguous profile URL)",
    )
    requires_context: bool = Field(
        default=False,
        description="Drop the match unless a positive context cue fired (for bare-numeric ids like QQ)",
    )


class CountryOverride(BaseModel):
    """Deep-merged onto the base pack when a country is resolved."""

    default_region: str | None = None
    patterns: list[PatternSpec] = Field(default_factory=list)
    validator: str | None = None


class Pack(BaseModel):
    """The full config for one ``SelectorType``."""

    selector_type: SelectorType
    priority: int = Field(ge=0, le=100, description="Resolver ordering on overlap; higher wins")
    base_confidence: float = Field(ge=0, le=1)
    max_confidence: float = Field(default=0.99, ge=0, le=1)
    normalizer: str
    validator: str | None = None
    patterns: list[PatternSpec] = Field(min_length=1)
    context: ContextConfig = Field(default_factory=ContextConfig)
    countries: dict[str, CountryOverride] = Field(default_factory=dict)
