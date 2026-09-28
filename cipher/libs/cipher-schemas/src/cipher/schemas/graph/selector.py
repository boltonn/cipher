"""Type-specific detail for an `entity` of type selector (1:1 with `entity`).

A selector is a strong typed identifier (phone, email, passport, IMEI, IBAN,
handle, ...). `normalized_value` plus `selector_type` is the blocking key used
during entity resolution and is unique within a dataset; `selector_subtype`
(telegram, btc_address, ...) is descriptive and optional.
"""

from datetime import datetime

from pydantic import Field

from cipher.schemas._base.base import BaseModel
from cipher.schemas.graph.ontology import SelectorSubtype, SelectorType


class SelectorBase(BaseModel):
    """Base selector detail schema."""

    entity_id: str = Field(description="The entity node this detail belongs to")
    dataset_id: str | None = Field(
        default=None,
        description="Dataset scope for uniqueness; null for analyst-attached selectors (external knowledge)",
    )
    selector_type: SelectorType
    selector_subtype: SelectorSubtype | None = Field(
        default=None, description="Specific provider/network/scheme, e.g. telegram, btc_address"
    )
    raw_value: str = Field(description="The selector as first seen")
    normalized_value: str = Field(description="Canonical form (E.164 phone, lowercased email, ...)")
    region_hint: str | None = Field(default=None, description="Region used to normalize, e.g. phone country")
    attributes: dict[str, str] = Field(
        default_factory=dict,
        description="Kind-specific facts from validation (iban country/bank, crypto network, phone carrier, ...)",
    )


class SelectorCreate(SelectorBase):
    """Selector detail creation schema."""

    pass


class SelectorUpdate(BaseModel):
    """Selector detail update schema."""

    raw_value: str | None = Field(default=None)
    region_hint: str | None = Field(default=None)
    attributes: dict[str, str] | None = Field(default=None)


class Selector(SelectorBase):
    """Selector detail model for API responses."""

    id: str
    date_created: datetime
    date_updated: datetime

    model_config = {"from_attributes": True}


class SelectorLinkRequest(BaseModel):
    """Attach a selector to an actor entity: create-or-reuse the selector node and its has_selector edge.

    An analyst link is knowledge about a real-world thing, not an observation in
    one ingest -- it carries no dataset. The selector node is dataset-agnostic
    and the ``has_selector`` edge is a manual, dataset-agnostic link.
    """

    selector_type: SelectorType
    selector_subtype: SelectorSubtype | None = Field(default=None)
    raw_value: str = Field(min_length=1, description="The selector as entered by the analyst")
    region_hint: str | None = Field(
        default=None, description="ISO-3166-1 alpha-2 country for phone normalization, e.g. 'US'"
    )


class SelectorRegion(BaseModel):
    """One phone-parsing region the normalizer accepts."""

    code: str = Field(description="ISO-3166-1 alpha-2 country code")
    calling_code: int = Field(description="ITU E.164 country calling code, e.g. 1 for US")
