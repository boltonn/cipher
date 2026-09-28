from typing import Any

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.geo import geojson_to_geom, geom_to_geojson, point_to_geom
from cipher.datastores.postgres.tables.file import FileTable
from cipher.datastores.postgres.tables.image import ImageTable
from cipher.datastores.postgres.tables.location import LocationTable
from cipher.datastores.postgres.utils import strip_null_bytes
from cipher.schemas.graph.location import Location, LocationCreate, LocationQuery, LocationUpdate

_UPSERT_KEYS = (
    "latitude",
    "longitude",
    "altitude",
    "geom",
    "geohash",
    "precision_m",
    "bearing",
    "pitch",
    "velocity",
    "velocity_accuracy",
    "horizontal_accuracy",
    "vertical_accuracy",
    "name",
    "date_recorded",
    "attributes",
)


def _row_values(payload: LocationCreate) -> dict[str, Any]:
    """LocationCreate -> column dict, resolving `geo_json`/lat-lon into a `geom`."""
    values = strip_null_bytes(payload.model_dump(by_alias=False))
    geo_json = values.pop("geo_json", None)
    if geo_json is not None:
        values["geom"] = geojson_to_geom(geo_json)
    else:
        values["geom"] = point_to_geom(latitude=values["latitude"], longitude=values["longitude"])
    return values


def _to_schema(row: LocationTable) -> Location:
    data = {c.name: getattr(row, c.name) for c in row.__table__.columns}
    geom = data.pop("geom", None)
    data["geo_json"] = geom_to_geojson(geom).model_dump(mode="json") if geom is not None else None
    return Location.model_validate(data)


class PostgresLocationRepository:
    """Postgres datastore for geolocated points."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_table(self):
        """Create the location table using SQLAlchemy metadata."""
        async with self.session.bind.begin() as conn:
            await conn.run_sync(LocationTable.metadata.create_all)

    async def get_count(self) -> int:
        """Total number of location rows."""
        result = await self.session.execute(select(func.count(LocationTable.id)))
        return result.scalar_one()

    async def add_location(self, payload: LocationCreate) -> Location:
        """Insert a single location row."""
        row = LocationTable(**_row_values(payload))
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return _to_schema(row)

    async def replace_file_locations(self, *, file_id: str, source: str, rows: list[LocationCreate]) -> int:
        """Delete a file's points for one `source` and re-insert `rows` (many points per file).

        Unlike `upsert_file_locations` (one point per file per source), this
        supports a document that mentions several coordinates. Idempotent per
        `(file_id, source)`. Does not commit.
        """
        await self.session.execute(
            delete(LocationTable).where(LocationTable.file_id == file_id, LocationTable.source == source)
        )
        payloads = [_row_values(r) for r in rows]
        if payloads:
            self.session.add_all(LocationTable(**p) for p in payloads)
        return len(payloads)

    async def upsert_file_locations(self, rows: list[LocationCreate]) -> int:
        """Insert points keyed by their source file, updating on `(file_id, source)`.

        Idempotent: re-running an extractor over the same files refreshes the
        coordinate rather than creating a duplicate.
        """
        payloads = [_row_values(r) for r in rows if r.file_id is not None]
        if not payloads:
            return 0
        # One row per (file_id, source): a conflict-target key repeated in a
        # single INSERT ... ON CONFLICT is rejected by Postgres.
        deduped = {(p["file_id"], p["source"]): p for p in payloads}
        stmt = pg_insert(LocationTable).values(list(deduped.values()))
        stmt = stmt.on_conflict_do_update(
            index_elements=["file_id", "source"],
            index_where=text("source <> 'TEXT_MENTION'"),
            set_={k: getattr(stmt.excluded, k) for k in _UPSERT_KEYS},
        )
        await self.session.execute(stmt)
        await self.session.commit()
        return len(deduped)

    async def query_locations(self, query: LocationQuery) -> list[Location]:
        """Points matching the viewer's filters."""
        where = []
        if query.bbox is not None:
            west, south, east, north = query.bbox
            where.append(func.ST_Intersects(LocationTable.geom, func.ST_MakeEnvelope(west, south, east, north, 4326)))
        if query.dataset_ids:
            where.append(LocationTable.dataset_id.in_(query.dataset_ids))
        if query.sources:
            where.append(LocationTable.source.in_(query.sources))
        if query.date_from is not None:
            where.append(LocationTable.date_recorded >= query.date_from)
        if query.date_to is not None:
            where.append(LocationTable.date_recorded <= query.date_to)

        stmt = (
            select(LocationTable)
            .where(*where)
            .order_by(LocationTable.date_recorded.desc().nullslast())
            .offset((query.page - 1) * query.limit)
            .limit(query.limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_to_schema(row) for row in rows]

    async def image_ids_for_files(self, file_ids: list[str]) -> dict[str, str]:
        """Map file_id -> image content id (sha256) for files that are images.

        Lets the map link a point back to the image viewer without storing a
        redundant image id on the location row.
        """
        wanted = {fid for fid in file_ids if fid}
        if not wanted:
            return {}
        rows = (
            await self.session.execute(
                select(FileTable.id, FileTable.sha256)
                .join(ImageTable, ImageTable.id == FileTable.sha256)
                .where(FileTable.id.in_(wanted))
            )
        ).all()
        return {file_id: sha256 for file_id, sha256 in rows}

    async def get_location(self, location_id: str) -> Location | None:
        """Fetch one location by id."""
        row = (
            await self.session.execute(select(LocationTable).where(LocationTable.id == location_id))
        ).scalar_one_or_none()
        return _to_schema(row) if row else None

    async def update_location(self, location_id: str, data: LocationUpdate) -> Location | None:
        """Patch a location row."""
        patch = strip_null_bytes(data.model_dump(exclude_unset=True, by_alias=False))
        if patch.get("latitude") is not None and patch.get("longitude") is not None:
            patch["geom"] = point_to_geom(latitude=patch["latitude"], longitude=patch["longitude"])
        if patch:
            await self.session.execute(update(LocationTable).where(LocationTable.id == location_id).values(**patch))
            await self.session.commit()
        return await self.get_location(location_id)

    async def delete_location(self, location_id: str) -> bool:
        """Delete a location row."""
        result = await self.session.execute(delete(LocationTable).where(LocationTable.id == location_id))
        await self.session.commit()
        return bool(result.rowcount)

    async def find_by_name(self, name: str, *, dataset_id: str | None = None) -> Location | None:
        """Exact (case-insensitive) match on a named location; prefers a dataset-agnostic row.

        Used by `resolve-event-links` to attach an `event_place` to a place that
        is already on the map. No geocoding -- a miss just leaves `raw_text`.
        """
        needle = name.strip().lower()
        if not needle:
            return None
        where = [func.lower(LocationTable.name) == needle]
        if dataset_id is not None:
            where.append((LocationTable.dataset_id == dataset_id) | (LocationTable.dataset_id.is_(None)))
        row = (
            await self.session.execute(
                select(LocationTable).where(*where).order_by(LocationTable.dataset_id.is_(None).desc()).limit(1)
            )
        ).scalar_one_or_none()
        return _to_schema(row) if row else None
