"""Shared: turn an EXIF-metadata dict into a `LocationCreate`.

Used by both `embed_images` (which parses EXIF anyway while preparing images)
and the standalone `extract_exif_locations` enrichment.
"""

from datetime import UTC, datetime

from cipher.schemas.graph.location import LocationCreate
from cipher.schemas.graph.ontology import LocationSource


def exif_location_create(meta: dict, *, file_id: str, dataset_id: str | None) -> LocationCreate | None:
    """Build a location row from a photo's EXIF GPS, or None when it has no usable fix."""
    lat, lon = meta.get("gps_latitude"), meta.get("gps_longitude")
    if lat is None or lon is None:
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
        return None

    recorded = meta.get("date_taken")
    if isinstance(recorded, datetime) and recorded.tzinfo is None:
        recorded = recorded.replace(tzinfo=UTC)

    return LocationCreate(
        file_id=file_id,
        dataset_id=dataset_id,
        latitude=lat,
        longitude=lon,
        altitude=meta.get("gps_altitude"),
        bearing=meta.get("gps_bearing"),
        velocity=meta.get("gps_speed"),
        horizontal_accuracy=meta.get("gps_h_accuracy"),
        source=LocationSource.EXIF,
        date_recorded=recorded if isinstance(recorded, datetime) else None,
    )
