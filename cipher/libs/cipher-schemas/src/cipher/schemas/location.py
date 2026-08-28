"""Type-specific detail for an `entity` of type location (1:1 with `entity`)."""

from datetime import datetime

from pydantic import Field

from cipher.schemas.base import BaseModel
from cipher.schemas.ontology import LocationSource


class LocationBase(BaseModel):
    """Base location detail schema."""

    entity_id: str = Field(description="The entity node this detail belongs to")
    address_text: str | None = Field(default=None, description="Free-text address or place description")
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    geohash: str | None = Field(default=None, max_length=12, description="Geohash of lat/lon, for coarse matching")
    source: LocationSource = Field(default=LocationSource.NAMED_MENTION, description="Where the coordinates/address came from")
    precision_m: float | None = Field(default=None, ge=0, description="Approximate positional uncertainty in metres")
    country: str | None = Field(default=None)
    admin_area: str | None = Field(default=None, description="State/province/region")


class LocationCreate(LocationBase):
    """Location detail creation schema."""

    pass


class LocationUpdate(BaseModel):
    """Location detail update schema."""

    address_text: str | None = Field(default=None)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    geohash: str | None = Field(default=None, max_length=12)
    source: LocationSource | None = Field(default=None)
    precision_m: float | None = Field(default=None, ge=0)
    country: str | None = Field(default=None)
    admin_area: str | None = Field(default=None)


class Location(LocationBase):
    """Location detail model for API responses."""

    id: str
    date_created: datetime
    date_updated: datetime

    model_config = {"from_attributes": True}
