"""A single geolocated point, from any source (mirrors shadowbot's `Location`).

A `Location` is standalone: it may reference a source `file` (a photo's EXIF GPS),
be the resolved detail of a knowledge-graph entity (`entity.location_id` points at
it), both, or neither. When a location *is* an entity it shares the entity's id.
Every location carries coordinates -- an address with no fix stays an unresolved
mention until it is geocoded.
"""

from datetime import datetime
from typing import Any

from geojson_pydantic.geometries import Geometry
from pydantic import Field

from cipher.schemas._base.base import BaseModel
from cipher.schemas._base.common import PaginatedResponse
from cipher.schemas.graph.ontology import LocationSource


class LocationBase(BaseModel):
    """Base location schema."""

    file_id: str | None = Field(default=None, description="Source file this point was extracted from")
    dataset_id: str | None = Field(default=None, description="Dataset the source belongs to")

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    altitude: float | None = Field(default=None, description="Metres above sea level")
    geo_json: Geometry | None = Field(default=None, description="Full geometry; set on read, optional on write")
    geohash: str | None = Field(default=None, max_length=12, description="Geohash of lat/lon, for coarse matching")
    precision_m: float | None = Field(default=None, ge=0, description="Approximate positional uncertainty in metres")

    bearing: int | None = Field(default=None, ge=0, le=359, description="Heading in degrees: 0 north, clockwise")
    pitch: float | None = Field(default=None, ge=-90, le=90, description="Tilt in degrees: 0 level, 90 up, -90 down")
    velocity: float | None = Field(default=None, ge=0, description="Speed over ground, m/s")
    velocity_accuracy: float | None = Field(default=None, ge=0, description="1-sigma uncertainty of velocity, m/s")
    horizontal_accuracy: float | None = Field(default=None, ge=0, description="1-sigma horizontal uncertainty, metres")
    vertical_accuracy: float | None = Field(default=None, ge=0, description="1-sigma altitude uncertainty, metres")

    name: str | None = Field(default=None, description="Human-readable place or facility name")
    category: str | None = Field(default=None, description="Semantic kind, e.g. 'home', 'camera', 'park'")
    address: str | None = Field(default=None, description="Free-text address or place description")
    city: str | None = Field(default=None)
    admin_area: str | None = Field(default=None, description="State/province/region")
    country: str | None = Field(default=None)
    tags: list[str] = Field(
        default_factory=list,
        description="Mirror of the location entity's tags (set them on the entity -- they carry provenance there)",
    )
    attributes: dict[str, Any] = Field(default_factory=dict, description="Source key/values (provenance, counts)")

    source: LocationSource = Field(
        default=LocationSource.NAME_MENTION, description="Where the coordinates/address came from"
    )
    source_id: str | None = Field(default=None, description="The provider's own identifier for this place")
    date_recorded: datetime | None = Field(
        default=None, description="When this point was observed (photo capture time, GPS ping time, call start)"
    )
    duration_seconds: float | None = Field(
        default=None, ge=0, description="How long the observation lasted from `date_recorded` (a call, a stay)"
    )


class LocationCreate(LocationBase):
    """Location creation schema."""

    pass


class LocationUpdate(BaseModel):
    """Location update schema."""

    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    altitude: float | None = Field(default=None)
    geohash: str | None = Field(default=None, max_length=12)
    precision_m: float | None = Field(default=None, ge=0)
    bearing: int | None = Field(default=None, ge=0, le=359)
    pitch: float | None = Field(default=None, ge=-90, le=90)
    velocity: float | None = Field(default=None, ge=0)
    velocity_accuracy: float | None = Field(default=None, ge=0)
    horizontal_accuracy: float | None = Field(default=None, ge=0)
    vertical_accuracy: float | None = Field(default=None, ge=0)
    name: str | None = Field(default=None)
    category: str | None = Field(default=None)
    address: str | None = Field(default=None)
    city: str | None = Field(default=None)
    admin_area: str | None = Field(default=None)
    country: str | None = Field(default=None)
    attributes: dict[str, Any] | None = Field(default=None)
    source: LocationSource | None = Field(default=None)
    source_id: str | None = Field(default=None)
    date_recorded: datetime | None = Field(default=None)
    duration_seconds: float | None = Field(default=None, ge=0)


class Location(LocationBase):
    """Location model for API responses."""

    id: str
    date_created: datetime
    date_updated: datetime

    model_config = {"from_attributes": True}


class LocationQuery(BaseModel):
    """Filter surface for the map viewer."""

    bbox: tuple[float, float, float, float] | None = Field(
        default=None, description="(west, south, east, north) in degrees"
    )
    dataset_ids: list[str] = Field(default_factory=list)
    sources: list[LocationSource] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    date_from: datetime | None = Field(default=None, description="Keep points with date_recorded at or after this")
    date_to: datetime | None = Field(default=None, description="Keep points with date_recorded at or before this")
    limit: int = Field(default=2_000, ge=1, le=10_000)
    page: int = Field(default=1, ge=1)


class PaginatedLocationsResponse(PaginatedResponse):
    """Paginated response for locations (table view)."""

    data: list[Location] = Field(description="List of locations")
