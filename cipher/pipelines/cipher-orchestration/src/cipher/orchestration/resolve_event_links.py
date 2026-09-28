"""Event-link resolution sweep: unresolved `event_participant` / `event_place` -> `entity` / `location`.

The counterpart to `resolve-entities` for the event layer. `extract-events`
leaves participants as `raw_name` / `raw_email` and places as `raw_text`; this
dataset-wide pass connects them to what the graph already knows:

* **participants** -- an email (iCalendar `mailto:`) is matched to the person /
  org that owns that `selector` (precise); failing that, a normalized-name match
  against an existing `person` then `organization` entity. Rooms and resources
  (`is_resource`) are skipped. Never creates an entity -- an unmatched name is
  left for Review, exactly like `resolve-entities`' untyped-name rule.
* **places** -- a normalized-name match against an existing `location`. There is
  no geocoder in-repo, so a miss just leaves `raw_text`.

Re-runnable: only reads `entity_id IS NULL` / `location_id IS NULL` rows, so a
second run is a no-op. `reset-events` clears everything `extract-events` created.
"""

from typing import TYPE_CHECKING

from loguru import logger

from cipher.datastores.postgres.repositories import (
    PostgresEntityRepository,
    PostgresEventRepository,
    PostgresLocationRepository,
)
from cipher.datastores.postgres.utils import normalize_name
from cipher.schemas.graph.ontology import EntityType
from cipher.schemas.graph.selector import SelectorType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_ACTOR_TYPES = (EntityType.PERSON, EntityType.ORGANIZATION)


def _normalize_email(value: str) -> str | None:
    """Best-effort email normalization; None when the address is unusable."""
    try:
        from pyselectors.normalize import normalize_email
    except ImportError:
        return value.strip().lower() or None
    try:
        return normalize_email(value) or None
    except Exception:
        return None


async def resolve_event_links_workflow(session: "AsyncSession", dataset_id: str) -> dict[str, int]:
    """Resolve a dataset's unresolved event participant/place links. Returns per-outcome counts."""
    event_repo = PostgresEventRepository(session=session)
    entity_repo = PostgresEntityRepository(session=session)
    location_repo = PostgresLocationRepository(session=session)

    participants = await event_repo.unresolved_participants(dataset_id)
    by_email = by_name = participants_left = skipped_resources = 0
    for participant in participants:
        if participant.is_resource:
            skipped_resources += 1
            continue

        entity = None
        normalized_email = _normalize_email(participant.raw_email) if participant.raw_email else None
        if normalized_email:
            entity = await entity_repo.search_by_selector(
                dataset_id=dataset_id, normalized_value=normalized_email, selector_type=SelectorType.EMAIL
            )
            matched_by = "email"
        if entity is None and participant.raw_name:
            normalized_name = normalize_name(participant.raw_name)
            for entity_type in _ACTOR_TYPES:
                entity = await entity_repo.find_by_normalized_name(
                    dataset_id=dataset_id, entity_type=entity_type, normalized_value=normalized_name
                )
                if entity is not None:
                    break
            matched_by = "name"

        if entity is None:
            participants_left += 1
            continue
        await event_repo.set_participant_entity(participant.id, entity.id)
        if matched_by == "email":
            by_email += 1
        else:
            by_name += 1

    places = await event_repo.unresolved_places(dataset_id)
    places_matched = places_left = 0
    for place in places:
        location = await location_repo.find_by_name(place.raw_text, dataset_id=dataset_id)
        if location is None:
            places_left += 1
            continue
        await event_repo.set_place_location(place.id, location.id)
        places_matched += 1

    await session.commit()

    counts = {
        "participants_by_email": by_email,
        "participants_by_name": by_name,
        "participants_left": participants_left,
        "resources_skipped": skipped_resources,
        "places_matched": places_matched,
        "places_left": places_left,
    }
    logger.success(f"Resolved event links for dataset {dataset_id}: {counts}")
    return counts
