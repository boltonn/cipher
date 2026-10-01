"""Websites are `domain` selectors, not organizations.

NER used to tag `Udemy.com`, `Target.com/terms` -- or `Towards` cut out of
`towardsdatascience.com` -- as organization/person names. New runs drop those spans
(`extract_entities._to_mention`) and the pattern pass records the site as a `domain`
selector. `reclassify_domains_workflow` repairs a dataset extracted before that:

  1. delete the web-address name mentions (their name groups leave the Resolve queue);
  2. run the domain pattern pass over the dataset's text, so every site becomes a
     `domain` selector mention;
  3. fold each website-named entity (`Udemy.com`) into the organization of the same
     name (`Udemy`); an auto-created one with no match and no mentions left is deleted;
  4. link domains to organizations (`link_domain_selectors`).

Idempotent: a re-run finds nothing left to move.
"""

import re
from collections import defaultdict

from loguru import logger
from pyselectors.domains import is_web_address, registrable_domain, site_name, web_host_containing
from sqlalchemy import delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from tqdm import tqdm

from cipher.datastores.postgres.repositories import (
    PostgresEntityRepository,
    PostgresGraphRepository,
    PostgresMentionRepository,
)
from cipher.datastores.postgres.repositories._merge import fold_entity
from cipher.datastores.postgres.tables.entity import EntityTable, is_canonical_entity
from cipher.datastores.postgres.tables.entity_match import EntityMatchTable
from cipher.datastores.postgres.tables.entity_relationship import EntityRelationshipTable
from cipher.datastores.postgres.tables.extracted_text import ExtractedTextTable
from cipher.datastores.postgres.tables.file import FileTable
from cipher.datastores.postgres.tables.mention import MentionTable
from cipher.datastores.postgres.tables.selector import SelectorTable
from cipher.schemas.graph.entity_match import EntityMatchStatus
from cipher.schemas.graph.entity_relationship import EntityRelationshipCreate
from cipher.schemas.graph.ontology import EntityType, RelationshipSource, RelationshipType, SelectorType

_DOMAINISH_SQL = r"[A-Za-z0-9-]\.[A-Za-z]{2,}"


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


async def _web_address_name_mentions(session: AsyncSession, dataset_id: str) -> list[tuple[str, str, str | None]]:
    """(mention id, normalized value, entity id) of every name mention that is really a website.

    A surface that is a whole address (`Udemy.com`) counts outright; any other span is checked
    at its offsets in the text, so `Towards` counts only where it sits in `towardsdatascience.com`.
    """
    rows = (
        await session.execute(
            select(
                MentionTable.id,
                MentionTable.surface_text,
                MentionTable.normalized_value,
                MentionTable.entity_id,
                MentionTable.mentioned_id,
                MentionTable.start_offset,
                MentionTable.end_offset,
            ).where(
                MentionTable.dataset_id == dataset_id,
                MentionTable.entity_attribute == "name",
                or_(MentionTable.surface_text.op("~")(_DOMAINISH_SQL), MentionTable.context.op("~")(_DOMAINISH_SQL)),
            )
        )
    ).all()
    found, by_text = [], defaultdict(list)
    for mention_id, surface, normalized, entity_id, text_id, start, end in rows:
        if is_web_address(surface):
            found.append((mention_id, normalized, entity_id))
        elif start is not None and end is not None:
            by_text[text_id].append((mention_id, normalized, entity_id, start, end))

    text_ids = list(by_text)
    for batch in range(0, len(text_ids), 500):
        contents = await session.execute(
            select(ExtractedTextTable.id, ExtractedTextTable.content).where(
                ExtractedTextTable.id.in_(text_ids[batch : batch + 500])
            )
        )
        for text_id, content in contents:
            found += [
                (mention_id, normalized, entity_id)
                for mention_id, normalized, entity_id, start, end in by_text[text_id]
                if end <= len(content) and web_host_containing(content, start, end)
            ]
    return found


async def _extract_domains(session: AsyncSession, dataset_id: str) -> int:
    """Domain-only pattern pass over every text in the dataset not already scanned for domains."""
    from cipher.orchestration.extract_selectors import _extract_text_selectors

    scanned = exists().where(
        MentionTable.mentioned_id == ExtractedTextTable.id,
        MentionTable.selector_type == SelectorType.DOMAIN,
    )
    texts = (
        await session.execute(
            select(ExtractedTextTable.id, ExtractedTextTable.file_id)
            .join(FileTable, FileTable.id == ExtractedTextTable.file_id)
            .where(FileTable.dataset_id == dataset_id, ~scanned)
        )
    ).all()
    entity_repo = PostgresEntityRepository(session=session)
    mention_repo = PostgresMentionRepository(session=session)
    selector_cache: dict[tuple, str] = {}
    written = 0
    for text_id, file_id in tqdm(texts, desc="Extracting domains", unit=" text"):
        extracted = await session.get(ExtractedTextTable, text_id)
        written += await _extract_text_selectors(
            dataset_id=dataset_id,
            file_id=file_id,
            extracted=extracted,
            entity_repo=entity_repo,
            mention_repo=mention_repo,
            selector_cache=selector_cache,
            types={SelectorType.DOMAIN},
        )
        session.expunge(extracted)
    return written


async def _fold_website_entities(session: AsyncSession, dataset_id: str, entity_ids: set[str]) -> dict[str, int]:
    """Fold website-named entities into the same-named organization, or drop empty auto-created ones."""
    candidates = (
        await session.execute(
            select(EntityTable.id, EntityTable.display_name, is_canonical_entity()).where(
                EntityTable.entity_type.in_([EntityType.ORGANIZATION, EntityType.PERSON]),
                or_(EntityTable.dataset_id == dataset_id, EntityTable.id.in_(entity_ids)),
            )
        )
    ).all()
    websites = [(entity_id, name, canonical) for entity_id, name, canonical in candidates if is_web_address(name)]
    orgs = (
        await session.execute(
            select(EntityTable.id, EntityTable.display_name, EntityTable.aliases).where(
                EntityTable.entity_type == EntityType.ORGANIZATION,
                or_(EntityTable.dataset_id == dataset_id, EntityTable.dataset_id.is_(None)),
            )
        )
    ).all()
    by_key: dict[str, set[str]] = defaultdict(set)
    for org_id, display_name, aliases in orgs:
        if not is_web_address(display_name):
            for name in {display_name, *(aliases or [])}:
                by_key[_compact(name)].add(org_id)

    counts = {"folded": 0, "deleted": 0, "kept": 0}
    for entity_id, name, canonical in websites:
        domain = registrable_domain(name) or name
        targets = by_key.get(_compact(site_name(domain)), set())
        if len(targets) == 1:
            await fold_entity(session, source_id=entity_id, target_id=next(iter(targets)))
            counts["folded"] += 1
            continue
        remaining = await session.scalar(select(func.count()).where(MentionTable.entity_id == entity_id))
        if not canonical and not remaining:
            await session.execute(delete(EntityTable).where(EntityTable.id == entity_id))
            counts["deleted"] += 1
        else:
            logger.info(f"Kept website-named entity {name!r} ({remaining} mentions, canonical={bool(canonical)})")
            counts["kept"] += 1
    await session.commit()
    return counts


async def reclassify_domains_workflow(session: AsyncSession, dataset_id: str, dry_run: bool = False) -> dict:
    """Move websites out of the person/organization graph and into `domain` selectors (see module doc)."""
    web_mentions = await _web_address_name_mentions(session, dataset_id)
    entity_ids = {entity_id for _, _, entity_id in web_mentions if entity_id}
    if dry_run:
        return {"web_address_name_mentions": len(web_mentions), "entities_touched": len(entity_ids)}

    names = {normalized for _, normalized, _ in web_mentions if normalized}
    for start in range(0, len(web_mentions), 5000):
        ids = [mention_id for mention_id, _, _ in web_mentions[start : start + 5000]]
        await session.execute(delete(MentionTable).where(MentionTable.id.in_(ids)))
    # pending suggestions for name groups that no longer have a mention
    orphaned = await session.execute(
        delete(EntityMatchTable).where(
            EntityMatchTable.dataset_id == dataset_id,
            EntityMatchTable.mention_id.is_(None),
            EntityMatchTable.status == EntityMatchStatus.PENDING,
            EntityMatchTable.normalized_value.in_(names),
            ~exists().where(
                MentionTable.dataset_id == dataset_id,
                MentionTable.entity_attribute == "name",
                MentionTable.normalized_value == EntityMatchTable.normalized_value,
            ),
        )
    )
    await session.commit()

    counts = {
        "name_mentions_deleted": len(web_mentions),
        "suggestions_deleted": orphaned.rowcount or 0,
        "domain_mentions_written": await _extract_domains(session, dataset_id),
        **await _fold_website_entities(session, dataset_id, entity_ids),
    }
    counts["domains_linked"] = await link_domain_selectors(session, dataset_id)
    logger.success(f"Reclassified websites: {counts}")
    return counts
