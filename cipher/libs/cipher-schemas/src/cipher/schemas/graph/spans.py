"""The analytics -> orchestration contract for extraction output.

Every entity/relation/selector extractor (`pyselectors`, `pygliner`, `nerd`,
...) emits these span types, so the ingestion pipeline can swap extractors
without changing how it builds `mention` / `entity_relationship` rows.

Offsets are character positions into the exact string that was analyzed --
for extracted document text that is `ExtractedText.content`, the same contract
`TextChunk.start_offset` / `end_offset` use.
"""

from pydantic import BaseModel, Field

from cipher.schemas.graph.ontology import SelectorSubtype, SelectorType

__all__ = ["EntitySpan", "RelationSpan", "SelectorSpan", "CoordinateSpan"]


class EntitySpan(BaseModel):
    """One entity mention found by an extractor, before resolution."""

    surface_text: str
    label: str = Field(description="The extractor's raw label (mapped to a type by the workflow)")
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=0)
    score: float = Field(ge=0, le=1, default=1.0)


class RelationSpan(BaseModel):
    """One directed relation between two entity spans."""

    label: str = Field(description="The extractor's raw relation label")
    head_text: str
    tail_text: str
    head_start: int = Field(ge=0)
    tail_start: int = Field(ge=0)
    score: float = Field(ge=0, le=1, default=1.0)


class SelectorSpan(BaseModel):
    """One selector found by a deterministic extractor."""

    selector_type: SelectorType
    selector_subtype: SelectorSubtype | None = Field(
        default=None, description="Specific provider/network/scheme, e.g. telegram, btc_address"
    )
    raw_value: str = Field(description="The selector exactly as it appeared")
    normalized_value: str = Field(description="Canonical form (E.164 phone, lowercased email, ...)")
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=0)
    confidence: float = Field(ge=0, le=1, default=1.0)
    region_hint: str | None = Field(default=None, description="Region used to normalize, e.g. phone country")
    attributes: dict[str, str] = Field(
        default_factory=dict,
        description="Kind-specific facts from validation (iban country/bank, crypto network, ip version, ...)",
    )


class CoordinateSpan(BaseModel):
    """One geographic coordinate found in text, normalized to decimal degrees.

    Not a selector -- coordinates resolve to `location` rows / `LOCATION`
    mentions, not `selector` entities.
    """

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    raw_value: str = Field(description="The coordinate exactly as it appeared")
    coordinate_format: str = Field(description="decimal | dms | cyrillic | cjk | labeled")
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=0)
    confidence: float = Field(ge=0, le=1, default=1.0)
