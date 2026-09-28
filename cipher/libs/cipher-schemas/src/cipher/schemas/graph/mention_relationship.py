"""A relation between two mention spans, captured at extraction time.

An extractor (an LLM pack, or GLiREL) reports a directed relation between two
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
    extractor: str | None = Field(default=None, description="Which extractor produced this (llm, gliner, ...)")
    extraction_model: str | None = Field(default=None, description="Model id/version, if any")


class MentionRelationshipCreate(MentionRelationshipBase):
    """Mention-relationship creation schema."""

    pass


class MentionRelationship(MentionRelationshipBase):
    """Mention-relationship model for API responses."""

    id: str
    date_created: datetime

    model_config = {"from_attributes": True}
