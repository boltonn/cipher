"""Resolve `location` name mentions to canonical place entities via the offline gazetteer.

Unlike people/organizations, places have an authoritative reference list, so
this is lookup, not scoring: each unresolved `location` `name` mention is
resolved *per mention* (`cipher.places.Gazetteer.resolve`, using the ~40 chars
either side -- `Dover, DE 19904` vs a `US, UK, DE` country list) and attached
to that place's entity. Ambiguous names (`Georgia`, `Washington`, a bare
`Wilmington`) are left unresolved rather than guessed.

Place entities are global (`dataset_id` NULL, source `import`) and shared by
every dataset: one `Delaware` node, found again by its `location.source_id`
(`wikidata:Q1393`, `geonames:4145381`, ...). Re-runnable: only reads
`entity_id IS NULL` mentions.
"""

from collections import Counter, defaultdict

from loguru import logger
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.repositories import PostgresEntityRepository, PostgresMentionRepository
from cipher.datastores.postgres.tables.location import LocationTable
from cipher.places import Gazetteer, Place, PlaceKind
from cipher.schemas.graph.entity import EntityCreate
from cipher.schemas.graph.location import LocationCreate
from cipher.schemas.graph.ontology import EntitySource, EntityType, LocationSource

_CONTEXT_CHARS = 40
_ATTACH_CHUNK = 10_000  # ids per UPDATE ... IN (...) -- asyncpg caps bind params at 32767

_UNRESOLVED_LOCATIONS_SQL = f"""
SELECT m.id, m.surface_text,
       substr(et.content, greatest(m.start_offset - {_CONTEXT_CHARS}, 0) + 1,
              m.start_offset - greatest(m.start_offset - {_CONTEXT_CHARS}, 0)) AS before,
       substr(et.content, m.end_offset + 1, {_CONTEXT_CHARS}) AS after
FROM mention m
LEFT JOIN extracted_text et ON et.id = m.mentioned_id AND m.mentioned_type = 'EXTRACTED_TEXT'
WHERE m.dataset_id = :ds AND m.entity_id IS NULL
  AND m.entity_type = 'LOCATION' AND m.entity_attribute = 'name'
"""


def _location_detail(place: Place) -> LocationCreate:
    return LocationCreate(
        latitude=place.latitude,
        longitude=place.longitude,
        name=place.name,
        category=place.kind.value,
        country=place.country_code,
        admin_area=place.admin1_code if place.kind in (PlaceKind.ADMIN1, PlaceKind.CITY) else None,
        city=place.name if place.kind is PlaceKind.CITY else None,
        source=LocationSource.NAME_MENTION,
        source_id=place.id,
    )


async def place_entities(session: AsyncSession, places: list[Place]) -> dict[str, str]:
    """Place id -> entity id, creating the global place entity (+ location row) on first sight."""
    if not places:
        return {}
    existing = await session.execute(
        select(LocationTable.source_id, LocationTable.id).where(
            LocationTable.source_id.in_([p.id for p in places]),
            LocationTable.dataset_id.is_(None),
            LocationTable.file_id.is_(None),
        )
    )
    entity_ids = dict(existing.tuples().all())
    entity_repo = PostgresEntityRepository(session=session)
    for place in places:
        if place.id not in entity_ids:
            entity = await entity_repo.create_entity(
                EntityCreate(
                    dataset_id=None,
                    entity_type=EntityType.LOCATION,
                    display_name=place.name,
                    source=EntitySource.IMPORT,
                ),
                detail=_location_detail(place),
            )
            entity_ids[place.id] = entity.id
    return entity_ids


async def resolve_locations_workflow(
    session: AsyncSession, dataset_id: str, *, gazetteer: Gazetteer | None = None
) -> dict[str, int]:
    """Attach a dataset's unresolved location name mentions to gazetteer places. Returns counts."""
    gazetteer = gazetteer or Gazetteer.load()
    rows = (await session.execute(text(_UNRESOLVED_LOCATIONS_SQL), {"ds": dataset_id})).all()

    mention_ids: dict[str, list[str]] = defaultdict(list)
    places: dict[str, Place] = {}
    kinds: Counter = Counter()
    for row in rows:
        place = gazetteer.resolve(row.surface_text, before=row.before or "", after=row.after or "")
        if place is not None:
            mention_ids[place.id].append(row.id)
            places[place.id] = place
            kinds[place.kind.value] += 1

    entity_ids = await place_entities(session, list(places.values()))
    mention_repo = PostgresMentionRepository(session=session)
    attached = 0
    for place_id, ids in mention_ids.items():
        for start in range(0, len(ids), _ATTACH_CHUNK):
            attached += await mention_repo.attach_many(ids[start : start + _ATTACH_CHUNK], entity_ids[place_id])

    counts = {
        "location_mentions": len(rows),
        "mentions_attached": attached,
        "places": len(places),
        **{f"attached_{kind}": n for kind, n in sorted(kinds.items())},
    }
    logger.success(f"Resolved locations for dataset {dataset_id}: {counts}")
    return counts
