"""Wire schemas for the selector-extraction service.

``SelectorSpan`` is the shared analytics contract from
``cipher.schemas.graph.spans``.
"""

from pydantic import BaseModel, Field

from cipher.schemas.graph.ontology import SelectorSubtype, SelectorType
from cipher.schemas.graph.spans import SelectorSpan

__all__ = [
    "SelectorType",
    "SelectorSubtype",
    "SelectorSpan",
    "SelectorExtractionRequest",
    "SelectorResolveRequest",
]


class SelectorExtractionRequest(BaseModel):
    """Request body for the ``/extract`` endpoint."""

    text: str
    language: str | None = Field(default=None, description="ISO-639-1 hint: context lexicon + default phone region")
    region: str | None = Field(default=None, description="Explicit ISO-3166 alpha-2 region (wins over language)")
    types: list[SelectorType] | None = Field(default=None, description="Restrict to these selector types")
    min_confidence: float = Field(default=0.0, ge=0, le=1, description="Drop spans scoring below this")


class SelectorResolveRequest(BaseModel):
    """Request body for ``/resolve`` -- normalize + validate + attributes for one bare value."""

    value: str = Field(min_length=1, description="The raw selector string")
    selector_type: SelectorType | None = Field(
        default=None, description="Force this type; omit to infer it from the value"
    )
    selector_subtype: SelectorSubtype | None = Field(default=None)
    language: str | None = Field(default=None)
    region: str | None = Field(default=None, description="ISO-3166 alpha-2 for phone / country validators")
