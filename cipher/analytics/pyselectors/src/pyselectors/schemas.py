"""Wire schemas for selector extraction.

`SelectorSpan` is the shared analytics contract from `cipher.schemas.spans`.
"""

from pydantic import BaseModel, Field

from cipher.schemas.ontology import SelectorKind
from cipher.schemas.spans import SelectorSpan

__all__ = ["SelectorKind", "SelectorSpan", "SelectorExtractionRequest"]


class SelectorExtractionRequest(BaseModel):
    """Request body for the `/extract` endpoint."""

    text: str
    language: str | None = Field(default=None, description="ISO-639-1 hint, used to pick a phone region")
    region: str | None = Field(default=None, description="Explicit ISO-3166 region for phone parsing")
