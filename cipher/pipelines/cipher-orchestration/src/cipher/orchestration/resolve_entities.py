"""Entity resolution sweep: unresolved name mentions -> entities.

Not a per-file enrichment -- a dataset-wide pass that needs a global view to
block. For each `(entity_type, normalized_value)` group of unresolved `name`
mentions:

  * **Typed** groups (`person` / `organization`, e.g. from a future NER pass):
    exact match on an existing entity's `display_name_normalized` -> attach; else,
    if creation is enabled and the group is trustworthy (any `structured_field`
    mention, or >= `min_mentions`), create a provisional entity and attach; else
    leave for Review.
  * **Untyped** groups (an email header display name -- "Nick Bolton" and
    "Medium Daily Digest" are indistinguishable): attach only if the name
    already matches an existing person *or* organization. Never auto-create --
    the person-vs-organization call is left to an analyst in Review.

Then link actors to the address they appeared next to in a header: wherever a
resolved name mention and a resolved `selector` mention share `(file_id,
field_path)` and the name resolved to a person/organization, upsert a
`has_selector` edge.

Provisional entities are dataset-scoped and (for persons) have no `person` row
yet (`entity.person_id` is null) -- they show up in the dataset's entity list
but not on the global Persons page until an analyst promotes one.

Re-runnable: only ever reads `entity_id IS NULL` mentions and upserts edges, so
a second run is a no-op. `reset-entities` clears everything it creates.
"""

from collections import Counter
from typing import TYPE_CHECKING

from loguru import logger
from tqdm import tqdm

from cipher.datastores.postgres.repositories import (
    PostgresEntityRepository,
    PostgresGraphRepository,
    PostgresMentionRepository,
)
from cipher.schemas.graph.entity import EntityCreate
from cipher.schemas.graph.ontology import EntitySource, EntityType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_NAME_TYPES = [EntityType.PERSON, EntityType.ORGANIZATION]
_ACTOR_TYPES = (EntityType.PERSON, EntityType.ORGANIZATION)


def _pick_display_name(surface_texts: list[str]) -> str:
    """Most common non-empty surface form, keeping its original casing."""
    counts = Counter(t.strip() for t in surface_texts if t and t.strip())
    return counts.most_common(1)[0][0] if counts else surface_texts[0]


async def resolve_entities_workflow(
    session: "AsyncSession",
    dataset_id: str,
    *,
    min_mentions: int = 2,
    create: bool = True,
    link_selectors: bool = True,
) -> dict[str, int]:
    """Resolve a dataset's unresolved name mentions to entities. Returns per-outcome counts."""
    mention_repo = PostgresMentionRepository(session=session)
    entity_repo = PostgresEntityRepository(session=session)

    groups = await mention_repo.unresolved_name_groups(dataset_id=dataset_id, entity_types=_NAME_TYPES)
    matched = created = attached = left = 0

    for group in tqdm(groups, desc="Resolving names", unit=" name"):
        entity_type = group["entity_type"]
        normalized_value = group["normalized_value"]
        mention_ids = group["mention_ids"]

        # Untyped (email-header) name: attach only to an existing person/org; the
        # analyst decides person vs organization in Review. Never auto-create.
        if entity_type is None:
            existing = None
            for candidate_type in _ACTOR_TYPES:
                existing = await entity_repo.find_by_normalized_name(
                    dataset_id=dataset_id, entity_type=candidate_type, normalized_value=normalized_value
                )
                if existing is not None:
                    break
            if existing is not None:
                attached += await mention_repo.attach_many(mention_ids, existing.id)
                matched += 1
            else:
                left += 1
            continue

        existing = await entity_repo.find_by_normalized_name(
            dataset_id=dataset_id, entity_type=entity_type, normalized_value=normalized_value
        )
        if existing is not None:
            attached += await mention_repo.attach_many(mention_ids, existing.id)
            matched += 1
            continue

        trustworthy = group["from_structured"] or len(mention_ids) >= min_mentions
        if not create or not trustworthy:
            left += 1
            continue

        entity = await entity_repo.create_entity(
            EntityCreate(
                dataset_id=dataset_id,
                entity_type=entity_type,
                display_name=_pick_display_name(group["surface_texts"]),
                source=EntitySource.EXTRACTION,
            )
        )
        attached += await mention_repo.attach_many(mention_ids, entity.id)
        created += 1

    edges = await PostgresGraphRepository(session=session).link_header_selectors(dataset_id) if link_selectors else 0

    counts = {
        "names_matched": matched,
        "entities_created": created,
        "mentions_attached": attached,
        "names_left_for_review": left,
        "has_selector_edges": edges,
    }
    logger.success(f"Resolved entities for dataset {dataset_id}: {counts}")
    return counts
