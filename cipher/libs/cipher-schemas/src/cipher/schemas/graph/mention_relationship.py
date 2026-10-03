"""A relation between two mention spans, captured at extraction time.

An extractor (an LLM pack, or GLiNER2.5) reports a directed relation between two
entity *spans* it found in the same text -- before either span is resolved to
an entity. A `MentionRelationship` records that assertion against the two
`mention` rows it connects, so the relation is not lost while resolution
catches up.

Once both endpoint mentions resolve to entities, the `resolve-entities` sweep
promotes each `MentionRelationship` into a `RelationshipCandidate` for the
analyst review queue -- with the endpoint types validated against the
ontology (`validate_relationship`). A relation whose endpoints never both
resolve simply stays here as latent evidence.
"""

from datetime import datetime

from pydantic import Field

from cipher.schemas._base.base import BaseModel
from cipher.schemas.graph.ontology import RelationshipType


class MentionRelationshipBase(BaseModel):
    """Base mention-relationship schema."""

    dataset_id: str
    src_mention_id: str = Field(description="Head span's mention row")
    dst_mention_id: str = Field(description="Tail span's mention row")
    relationship_type: RelationshipType
    directed: bool = Field(default=True)
    confidence: float = Field(default=1.0, ge=0, le=1)
    file_id: str | None = Field(default=None, description="Denormalized owning file")
    context: str | None = Field(default=None, description="Windowed snippet spanning both endpoint spans")
    attributes: dict = Field(
        default_factory=dict, description="Edge attributes to carry onto the entity edge, e.g. role"
    )
    extractor: str | None = Field(default=None, description="Which extractor produced this (llm, gliner, ...)")
    extraction_model: str | None = Field(default=None, description="Model id/version, if any")
    date_reviewed: datetime | None = Field(
        default=None, description="An analyst accepted or dismissed it as a name-level suggestion; never re-offered"
    )


class MentionRelationshipCreate(MentionRelationshipBase):
    """Mention-relationship creation schema."""

    pass


class MentionRelationship(MentionRelationshipBase):
    """Mention-relationship model for API responses."""

    id: str
    date_created: datetime

    model_config = {"from_attributes": True}


class EvidenceSpan(BaseModel):
    """One endpoint mention of a relation, with its offsets into the source text."""

    mention_id: str
    surface_text: str
    start_offset: int | None = Field(default=None)
    end_offset: int | None = Field(default=None)


class RelationshipEvidence(BaseModel):
    """A source passage behind a proposed edge: where the extractor saw the two names together."""

    mention_relationship_id: str | None = Field(default=None, description="None for a whole-email source")
    dataset_id: str
    file_id: str | None = Field(default=None)
    extractor: str | None = Field(default=None)
    confidence: float
    attributes: dict = Field(default_factory=dict)
    src: EvidenceSpan | None = Field(default=None, description="Head span; None for a whole-email source")
    dst: EvidenceSpan | None = Field(default=None)
    snippet: str = Field(description="Source text around both spans (the stored context when there is no text)")
    snippet_offset: int = Field(default=0, description="Offset of `snippet` in the source text; spans are absolute")
    subject: str | None = Field(default=None, description="Email subject, when the source is an email")
    sender: str | None = Field(default=None, description="Email sender name/address, when the source is an email")
    date_sent: datetime | None = Field(default=None)
