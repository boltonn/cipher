"""Wire schemas for the pygliner service.

`EntitySpan` / `RelationSpan` are the shared analytics contract from
`cipher.schemas.spans` -- re-exported here so `pygliner` and `nerd` emit the
identical shape the ingestion pipeline consumes.
"""

from pydantic import BaseModel, Field

from cipher.schemas.ontology import default_ner_labels, default_relation_labels
from cipher.schemas.spans import EntitySpan, RelationSpan

__all__ = ["EntitySpan", "RelationSpan", "NerRequest", "RelationRequest"]


class NerRequest(BaseModel):
    """Request body for `POST /infer`."""

    text: str
    labels: list[str] = Field(default_factory=default_ner_labels)
    threshold: float = Field(default=0.5, ge=0, le=1)


class RelationRequest(BaseModel):
    """Request body for `POST /relations`.

    `entities` are the spans to consider as relation endpoints -- normally the
    output of a prior `/infer` call.
    """

    text: str
    entities: list[EntitySpan]
    labels: list[str] = Field(default_factory=default_relation_labels)
    threshold: float = Field(default=0.5, ge=0, le=1)
