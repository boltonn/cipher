"""Wire schemas for the nerd service.

`EntitySpan` is the shared analytics contract from `cipher.schemas.spans`, so
`nerd` output is interchangeable with `pygliner` in the ingestion pipeline.
"""

from pydantic import BaseModel, Field

from cipher.schemas.spans import EntitySpan

__all__ = ["EntitySpan", "NerdRequest"]


class NerdRequest(BaseModel):
    """Request body for `POST /infer`."""

    text: str
    threshold: float = Field(default=0.5, ge=0, le=1, description="Minimum aggregated span score")
