"""The geospatial surface: query geolocated points for the map viewer.

The map shows observed coordinates: EXIF GPS, lat/longs written in text, geocoded
addresses, device fixes. Gazetteer places (the city/country behind a resolved
place name) keep a `location` row as their entity's detail but are not points.
"""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Response

from cipher.api.deps.postgres import LocationDatastoreDep
from cipher.schemas._base.exceptions import EntityNotFoundError
from cipher.schemas.graph.location import Location, LocationQuery, LocationUpdate
from cipher.schemas.graph.ontology import LocationSource

router = APIRouter(prefix="/locations", tags=["locations"])


def _parse_bbox(raw: str | None) -> tuple[float, float, float, float] | None:
    if not raw:
        return None
    parts = raw.split(",")
    try:
        west, south, east, north = (float(p) for p in parts)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="bbox must be 'west,south,east,north'") from exc
    return west, south, east, north


@router.get("", summary="Query locations as GeoJSON")
async def query_locations(
    datastore: LocationDatastoreDep,
    bbox: Annotated[str | None, Query(description="west,south,east,north in degrees")] = None,
    dataset_ids: Annotated[list[str] | None, Query(alias="datasetIds")] = None,
    sources: Annotated[list[LocationSource] | None, Query()] = None,
    categories: Annotated[list[str] | None, Query()] = None,
    date_from: Annotated[datetime | None, Query(alias="dateFrom")] = None,
    date_to: Annotated[datetime | None, Query(alias="dateTo")] = None,
    limit: Annotated[int, Query(ge=1, le=10000)] = 2000,
    page: Annotated[int, Query(ge=1)] = 1,
) -> dict[str, Any]:
    """Return matching points as a GeoJSON FeatureCollection for the map."""
    query = LocationQuery(
        bbox=_parse_bbox(bbox),
        dataset_ids=dataset_ids or [],
        sources=sources or [],
        categories=categories or [],
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        page=page,
    )
    locations = await datastore.query_locations(query)
    image_ids = await datastore.image_ids_for_files([loc.file_id for loc in locations if loc.file_id])
    features = [
        {
            "type": "Feature",
            "geometry": loc.geo_json.model_dump(mode="json") if loc.geo_json else None,
            "properties": {
                "id": loc.id,
                "name": loc.name,
                "category": loc.category,
                "source": loc.source,
                "dateRecorded": loc.date_recorded.isoformat() if loc.date_recorded else None,
                "durationSeconds": loc.duration_seconds,
                "bearing": loc.bearing,
                "velocity": loc.velocity,
                "altitude": loc.altitude,
                "fileId": loc.file_id,
                "imageId": image_ids.get(loc.file_id) if loc.file_id else None,
                "datasetId": loc.dataset_id,
            },
        }
        for loc in locations
        if loc.geo_json is not None
    ]
    return {"type": "FeatureCollection", "features": features}


@router.get("/categories", summary="Get the distinct categories present among locations", response_model=list[str])
async def get_location_categories(datastore: LocationDatastoreDep) -> list[str]:
    """Distinct location categories, most common first."""
    return await datastore.get_categories()


@router.get("/{location_id}", summary="Get a location", response_model=Location)
async def get_location(location_id: str, datastore: LocationDatastoreDep) -> Location:
    """Fetch a single location row."""
    location = await datastore.get_location(location_id)
    if location is None:
        raise EntityNotFoundError("Location", location_id)
    return location


@router.patch("/{location_id}", summary="Update a location", response_model=Location)
async def update_location(location_id: str, data: LocationUpdate, datastore: LocationDatastoreDep) -> Location:
    """Patch a location's name, category, address, or coordinates."""
    location = await datastore.update_location(location_id, data)
    if location is None:
        raise EntityNotFoundError("Location", location_id)
    return location


@router.delete("/{location_id}", summary="Delete a location", status_code=204)
async def delete_location(location_id: str, datastore: LocationDatastoreDep) -> Response:
    """Delete a location row."""
    if not await datastore.delete_location(location_id):
        raise EntityNotFoundError("Location", location_id)
    return Response(status_code=204)
