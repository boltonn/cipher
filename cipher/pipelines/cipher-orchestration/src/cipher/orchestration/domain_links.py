"""Link `domain` selectors to the organization named like the site (`bestbuy.com` -> Best Buy).

Run at the end of `extract-selectors`, once a dataset's websites are known.
"""

import re
from collections import defaultdict

from pyselectors.domains import is_web_address, site_name
from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.repositories import PostgresGraphRepository
from cipher.datastores.postgres.tables.entity import EntityTable, is_canonical_entity
from cipher.datastores.postgres.tables.entity_relationship import EntityRelationshipTable
from cipher.datastores.postgres.tables.selector import SelectorTable
from cipher.schemas.graph.entity_relationship import EntityRelationshipCreate
from cipher.schemas.graph.ontology import EntityType, RelationshipSource, RelationshipType, SelectorType


def _compact(name: str) -> str:
    """`Best Buy` / `bestbuy.com` -> `bestbuy`-style key: lowercase alphanumerics only."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


async def link_domain_selectors(session: AsyncSession, dataset_id: str) -> int:
    """Link each unlinked `domain` selector to the one organization named like the site.

    `bestbuy.com` -> `Best Buy`, `deeplearning.ai` -> `DeepLearning.AI`. A canonical
    organization wins over auto-created ones; an ambiguous or missing match stays unlinked.
    Returns edges written.
    """
    domains = (
        await session.execute(
            select(SelectorTable.entity_id, SelectorTable.normalized_value).where(
                SelectorTable.selector_type == SelectorType.DOMAIN,
                or_(SelectorTable.dataset_id == dataset_id, SelectorTable.dataset_id.is_(None)),
                ~exists().where(
                    EntityRelationshipTable.dst_entity_id == SelectorTable.entity_id,
                    EntityRelationshipTable.relationship_type == RelationshipType.HAS_SELECTOR,
                ),
            )
        )
    ).all()
    if not domains:
        return 0

    orgs = (
        await session.execute(
            select(EntityTable.id, EntityTable.display_name, EntityTable.aliases, is_canonical_entity()).where(
                EntityTable.entity_type == EntityType.ORGANIZATION,
                or_(EntityTable.dataset_id == dataset_id, EntityTable.dataset_id.is_(None)),
            )
        )
    ).all()
    by_key: dict[str, set[tuple[str, bool]]] = defaultdict(set)
    for org_id, display_name, aliases, canonical in orgs:
        if is_web_address(display_name):
            continue
        for name in {display_name, *(aliases or [])}:
            by_key[_compact(name)].add((org_id, bool(canonical)))

    graph = PostgresGraphRepository(session=session)
    linked = 0
    for selector_id, domain in domains:
        hits = by_key.get(_compact(site_name(domain)), set()) | by_key.get(_compact(domain), set())
        canonical = {org_id for org_id, is_canonical in hits if is_canonical}
        chosen = canonical or {org_id for org_id, _ in hits}
        if len(chosen) != 1:
            continue
        await graph.upsert_relationship(
            EntityRelationshipCreate(
                dataset_id=dataset_id,
                src_entity_id=chosen.pop(),
                dst_entity_id=selector_id,
                relationship_type=RelationshipType.HAS_SELECTOR,
                source=RelationshipSource.SELECTOR_INFERENCE,
            )
        )
        linked += 1
    return linked
