"""Backfill `location` rows from `image` EXIF coordinates already in the DB.

`embed_images` writes a location row for every geotagged photo it processes, but
images embedded before that wiring existed still carry `gps_latitude` /
`gps_longitude` on the `image` row with no matching point. This walks those and
upserts the missing locations. Idempotent (keyed on `(file_id, source)`).
"""

from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy import select

from cipher.datastores.postgres.repositories import PostgresLocationRepository
from cipher.datastores.postgres.tables.file import FileTable
from cipher.datastores.postgres.tables.image import ImageTable
from cipher.schemas.graph.location import LocationCreate
from cipher.schemas.graph.ontology import LocationSource

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def backfill_exif_locations(session: "AsyncSession", dataset_id: str | None = None) -> int:
    """Upsert a location for every image with EXIF coordinates. Returns rows written."""
    stmt = (
        select(
            FileTable.id,
            FileTable.dataset_id,
            ImageTable.gps_latitude,
            ImageTable.gps_longitude,
            ImageTable.gps_altitude,
            ImageTable.date_taken,
        )
        .join(FileTable, FileTable.sha256 == ImageTable.id)
        .where(ImageTable.gps_latitude.isnot(None), ImageTable.gps_longitude.isnot(None))
    )
    if dataset_id is not None:
        stmt = stmt.where(FileTable.dataset_id == dataset_id)

    rows = (await session.execute(stmt)).all()
    # One file per image content is enough -- any file with these bytes is an
    # equally valid representative (same rule the image repo uses).
    by_file: dict[str, LocationCreate] = {}
    for file_id, ds_id, lat, lon, alt, date_taken in rows:
        by_file[file_id] = LocationCreate(
            file_id=file_id,
            dataset_id=ds_id,
            latitude=lat,
            longitude=lon,
            altitude=alt,
            source=LocationSource.EXIF,
            date_recorded=date_taken,
        )

    written = await PostgresLocationRepository(session).upsert_file_locations(rows=list(by_file.values()))
    logger.success(f"Backfilled {written} EXIF locations")
    return written
