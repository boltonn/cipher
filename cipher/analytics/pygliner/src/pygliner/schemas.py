"""Wire schemas for the pygliner service.

`EntitySpan` / `RelationSpan` are the shared analytics contract from
`cipher.schemas.graph.spans` -- re-exported here so `pygliner` and `nerd` emit the
identical shape the ingestion pipeline consumes.
"""

from pydantic import BaseModel, Field

from cipher.schemas.graph.ontology import default_ner_labels, default_relation_labels
from cipher.schemas.graph.spans import EntitySpan, RelationSpan

__all__ = ["EntitySpan", "RelationSpan", "NerRequest", "ExtractRequest", "ExtractResponse", "ClassifyRequest"]


class NerRequest(BaseModel):
    """Request body for `POST /infer`."""

    text: str
    labels: list[str] = Field(default_factory=default_ner_labels)
    threshold: float = Field(default=0.65, ge=0, le=1)


class ExtractRequest(NerRequest):
    """Request body for `POST /extract`: entities and ontology-typed relations in one joint pass."""

    relation_labels: list[str] = Field(default_factory=default_relation_labels)


class ExtractResponse(BaseModel):
    """Response body for `POST /extract`."""

    entities: list[EntitySpan]
    relations: list[RelationSpan]


class ClassifyRequest(BaseModel):
    """Request body for `POST /classify`: zero-shot labels, each with a description of what it covers."""

    texts: list[str]
    labels: dict[str, str] = Field(description="Label name -> description")
