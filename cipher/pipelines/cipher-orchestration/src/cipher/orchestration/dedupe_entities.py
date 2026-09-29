"""Entity->entity dedup sweep: provisional entities -> canonical entities.

`resolve-entities` mints a *provisional* entity when a trustworthy name group has
no canonical match. Nothing then re-checks that stub against the real people /
orgs / places -- `resolve-entities` only scores unresolved *mentions*, and the
stub's mentions are already attached to it.

This pass closes that gap. For each provisional entity (`source=extraction`, not
bridged to a person/location):

1. **Block** -- `get_resolution_candidates(name=stub.display_name)`, then keep
   only canonical targets (bridged, or `source=manual`).
2. **Score** -- the same Fellegi-Sunter scorer, fed the stub's aggregate signals
   (its `has_selector` values, its co-mentioned neighbours, its aliases).
3. **Propose** -- a pending `entity_match` row with `provisional_entity_id` set,
   one per canonical candidate over `review_low`. Never auto: a merge is
   destructive, always analyst-reviewed.

Confirming a proposal runs `PostgresEntityRepository.merge_entities`. A pair an
analyst already rejected (here or as a name-group match) is not re-proposed.
"""

import asyncio
from collections import Counter

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tqdm import tqdm

from cipher.datastores.postgres.repositories import (
    PostgresEntityMatchRepository,
    PostgresEntityRepository,
)
from cipher.datastores.postgres.tables.entity import EntityTable, is_canonical_entity
from cipher.datastores.postgres.tables.mention import MentionTable
from cipher.orchestration.entity_resolution import (
    CandidateScoringInput,
    MentionScoringInput,
    build_explanation,
    decide,
    dominant_method,
    score_candidate,
)
from cipher.orchestration.resolve_entities import _candidate_details, _group_neighbours
from cipher.schemas.graph.entity_match import EntityMatchCreate
from cipher.schemas.graph.entity_resolution import (
    DEFAULT_RESOLUTION_CONFIG,
    EntityResolutionConfig,
)
from cipher.schemas.graph.ontology import EntitySource, EntityType

_MERGE_ROWS_PER_STUB = 5
_DEDUPE_TYPES = (EntityType.PERSON, EntityType.ORGANIZATION, EntityType.LOCATION)


async def _stub_mention_ids(session: AsyncSession, entity_id: str) -> list[str]:
    rows = (await session.execute(select(MentionTable.id).where(MentionTable.entity_id == entity_id))).scalars()
    return list(rows)


async def _name_frequency(session: AsyncSession, entity_type: EntityType, normalized: str) -> int:
    return (
        await session.execute(
            select(func.count())
            .select_from(EntityTable)
            .where(
                EntityTable.entity_type == entity_type,
                EntityTable.display_name_normalized == normalized,
            )
        )
    ).scalar_one() or 1


async def _canonical_ids(session: AsyncSession, entity_ids: list[str]) -> set[str]:
    """Of `entity_ids`, the ones worth merging *into* -- bridged or manually made."""
    if not entity_ids:
        return set()
    rows = (
        await session.execute(
            select(EntityTable.id).where(
                EntityTable.id.in_(entity_ids),
                is_canonical_entity(),
            )
        )
    ).scalars()
    return set(rows)


async def _dedupe_stub(
    session: AsyncSession,
    stub: EntityTable,
    *,
    config: EntityResolutionConfig,
    entity_repo: PostgresEntityRepository,
    ematch_repo: PostgresEntityMatchRepository,
    dataset_id: str,
) -> Counter:
    out: Counter = Counter()
    out["stubs_scanned"] += 1

    candidates = await entity_repo.get_resolution_candidates(
        name=stub.display_name,
        dataset_id=dataset_id,
        entity_type=stub.entity_type,
        limit=20,
    )
    cand_ids = [c.entity.id for c in candidates if c.entity.id != stub.id]
    canonical = await _canonical_ids(session, cand_ids)
    blocked = await ematch_repo.rejected_merge_targets(
        dataset_id=dataset_id,
        provisional_entity_id=stub.id,
        normalized_name=stub.display_name_normalized,
    )
    targets = [c for c in candidates if c.entity.id in canonical and c.entity.id not in blocked]
    if not targets:
        await ematch_repo.prune_merge_pending(
            dataset_id=dataset_id, provisional_entity_id=stub.id, keep_entity_ids=set()
        )
        return out

    stub_detail = (await _candidate_details(session, [stub.id])).get(stub.id)
    mention_ids = await _stub_mention_ids(session, stub.id)
    neighbours = await _group_neighbours(session, mention_ids)
    mi = MentionScoringInput(
        name=stub.display_name,
        normalized_name=stub.display_name_normalized,
        entity_type=stub.entity_type,
        provenance="text",
        selector_values=stub_detail.selector_values if stub_detail else frozenset(),
        neighbor_entity_ids=neighbours | (stub_detail.neighbour_ids if stub_detail else frozenset()),
        attributes=stub_detail.attributes if stub_detail else {},
        name_df=await _name_frequency(session, stub.entity_type, stub.display_name_normalized),
    )

    detail = await _candidate_details(session, [c.entity.id for c in targets])
    scored = []
    for c in targets:
        d = detail.get(c.entity.id)
        scored.append(
            score_candidate(
                mi,
                CandidateScoringInput(
                    entity_id=c.entity.id,
                    entity_type=c.entity.entity_type,
                    display_name=c.entity.display_name,
                    aliases=d.aliases if d else (),
                    selector_values=d.selector_values if d else frozenset(),
                    neighbor_entity_ids=d.neighbour_ids if d else frozenset(),
                    attributes=d.attributes if d else {},
                    trigram_score=c.trigram_score,
                    blocked_by=tuple(c.blocked_by),
                ),
                config,
            )
        )
    decide(scored, config)
    live = sorted(
        (s for s in scored if not s.vetoed and s.score >= config.review_low),
        key=lambda s: s.score,
        reverse=True,
    )[:_MERGE_ROWS_PER_STUB]
    runner_up = live[1].score if len(live) > 1 else None

    for sc in live:
        await ematch_repo.create_merge_match(
            EntityMatchCreate(
                dataset_id=dataset_id,
                entity_id=sc.entity_id,
                provisional_entity_id=stub.id,
                similarity_score=sc.score,
                match_method=dominant_method(sc),
                explanation=build_explanation(
                    sc, candidates_considered=len(live), runner_up_score=runner_up, config=config
                ),
            )
        )
    await ematch_repo.prune_merge_pending(
        dataset_id=dataset_id, provisional_entity_id=stub.id, keep_entity_ids={s.entity_id for s in live}
    )
    if live:
        out["merge_proposals"] += len(live)
        out["stubs_with_candidates"] += 1
    return out


async def dedupe_entities_workflow(
    session: AsyncSession,
    dataset_id: str,
    *,
    config: EntityResolutionConfig | None = None,
) -> dict[str, int]:
    """Score every provisional entity in `dataset_id` against canonical entities."""
    config = config or DEFAULT_RESOLUTION_CONFIG
    entity_repo = PostgresEntityRepository(session)
    ematch_repo = PostgresEntityMatchRepository(session)

    stubs = (
        (
            await session.execute(
                select(EntityTable).where(
                    EntityTable.dataset_id == dataset_id,
                    EntityTable.source == EntitySource.EXTRACTION,
                    EntityTable.entity_type.in_(_DEDUPE_TYPES),
                    EntityTable.person_id.is_(None),
                    EntityTable.location_id.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )

    totals: Counter = Counter()
    for stub in tqdm(stubs, desc="Deduping entities", unit=" stub"):
        totals += await _dedupe_stub(
            session,
            stub,
            config=config,
            entity_repo=entity_repo,
            ematch_repo=ematch_repo,
            dataset_id=dataset_id,
        )
        await asyncio.sleep(0)

    result = {
        "stubs_scanned": totals["stubs_scanned"],
        "stubs_with_candidates": totals["stubs_with_candidates"],
        "merge_proposals": totals["merge_proposals"],
    }
    logger.success(f"Deduped entities for dataset {dataset_id}: {result}")
    return result
