"""Conversions between GeoAlchemy2 geometry columns and geojson-pydantic models."""

from typing import Any

from geoalchemy2.elements import WKBElement
from geoalchemy2.shape import from_shape, to_shape
from geojson_pydantic import Point
from geojson_pydantic.geometries import Geometry, parse_geometry_obj
from shapely.geometry import mapping, shape

SRID = 4326


def point_to_geom(*, latitude: float, longitude: float) -> WKBElement:
    """Build a WKBElement POINT for storage from a lat/lon pair."""
    return from_shape(shape({"type": "Point", "coordinates": [longitude, latitude]}), srid=SRID)


def geojson_to_geom(geometry: Geometry | dict[str, Any]) -> WKBElement:
    """Convert any GeoJSON geometry (model or dict) into a WKBElement for storage."""
    raw = geometry if isinstance(geometry, dict) else geometry.model_dump(mode="json")
    return from_shape(shape(raw), srid=SRID)


def geom_to_geojson(geom: Any) -> Geometry:
    """Convert a stored geometry column value into the matching geojson-pydantic model."""
    return parse_geometry_obj(mapping(to_shape(geom)))


def geom_to_point(geom: Any) -> Point:
    """Convert a stored geometry column value into a GeoJSON Point."""
    return Point(**mapping(to_shape(geom)))
