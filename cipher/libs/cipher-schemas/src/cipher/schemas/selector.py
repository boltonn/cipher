"""Type-specific detail for an `entity` of type selector (1:1 with `entity`).

A selector is a strong typed identifier (phone, email, passport, IMEI, IBAN,
handle, ...). `normalized_value` plus `selector_kind` is the blocking key used
during entity resolution and is unique within a dataset.
"""

from datetime import datetime

from pydantic import Field

from cipher.schemas.base import BaseModel
from cipher.schemas.ontology import SelectorKind


class SelectorBase(BaseModel):
    """Base selector detail schema."""

    entity_id: str = Field(description="The entity node this detail belongs to")
    dataset_id: str = Field(description="Dataset scope for the uniqueness of the normalized value")
    selector_kind: SelectorKind
    raw_value: str = Field(description="The selector as first seen")
    normalized_value: str = Field(description="Canonical form (E.164 phone, lowercased email, ...)")
    region_hint: str | None = Field(default=None, description="Region used to normalize, e.g. phone country")


class SelectorCreate(SelectorBase):
    """Selector detail creation schema."""

    pass


class SelectorUpdate(BaseModel):
    """Selector detail update schema."""

    raw_value: str | None = Field(default=None)
    region_hint: str | None = Field(default=None)


class Selector(SelectorBase):
    """Selector detail model for API responses."""

    id: str
    date_created: datetime
    date_updated: datetime

    model_config = {"from_attributes": True}
