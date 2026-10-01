"""Entity resolution sweep: unresolved name mentions -> entities.

A dataset-wide pass (not a per-file enrichment -- blocking needs a global view).
For each `(entity_type, normalized_value)` group of unresolved `name` mentions:

1. **Block** -- `PostgresEntityRepository.get_resolution_candidates` unions
   selector, exact-name, `entity_name_key` and trigram candidates.
2. **Score** -- the Fellegi-Sunter scorer grades each candidate into features +
   a `[0,1]` score (`cipher.orchestration.entity_resolution`).
3. **Decide** -- `decide()` bands the ranked list:
   * `auto` (only the exact-selector-on-structured-field rule) -> attach the whole
     group to the entity now + a confirmed group-level `entity_match` audit row;
   * `review` -> a pending group-level `entity_match` per candidate for the queue;
   * nothing clears `review_low` -> a provisional entity for a trustworthy typed
     group (a structured mention, or >= `min_mentions`), else leave for Review.
4. `link_header_selectors` + promote extractor relations to candidates.

Re-runnable: only reads `entity_id IS NULL` mentions and `on_conflict_do_nothing`
on the group key, so a second run is a no-op. `reset-entities` clears it all.
"""

import asyncio
from collections import Counter
from typing import NamedTuple

from loguru import logger
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from tqdm import tqdm

from cipher.datastores.postgres.repositories import (
    PostgresEntityMatchRepository,
    PostgresEntityRepository,
    PostgresGraphRepository,
    PostgresMentionRelationshipRepository,
    PostgresMentionRepository,
)
from cipher.datastores.postgres.tables.entity import EntityTable, is_canonical_entity
from cipher.datastores.postgres.tables.entity_name_key import EntityNameKeyTable
from cipher.datastores.postgres.tables.entity_relationship import EntityRelationshipTable
from cipher.datastores.postgres.tables.mention import MentionTable
from cipher.datastores.postgres.tables.mention_relationship import MentionRelationshipTable
from cipher.datastores.postgres.tables.selector import SelectorTable
from cipher.names import entity_keys
from cipher.orchestration.entity_resolution import (
    CandidateScoringInput,
    MentionScoringInput,
    ScoredCandidate,
    build_explanation,
    decide,
    score_candidate,
)
from cipher.schemas.graph.entity import EntityCreate
from cipher.schemas.graph.entity_match import EntityMatchCreate
from cipher.schemas.graph.entity_resolution import (
    DEFAULT_RESOLUTION_CONFIG,
    EntityResolutionConfig,
    ResolutionBand,
)
from cipher.schemas.graph.ontology import EntitySource, EntityType, RelationshipType

_NAME_TYPES = [EntityType.PERSON, EntityType.ORGANIZATION]
_REVIEW_ROWS_PER_GROUP = 5
_KEY_PROBE_CHUNK = 10000  # single-column key values per IN clause


def _pick_display_name(surface_texts: list[str]) -> str:
    """Most common non-empty surface form, keeping its original casing."""
    counts = Counter(t.strip() for t in surface_texts if t and t.strip())
    return counts.most_common(1)[0][0] if counts else surface_texts[0]


def _provenance_for_group(group: dict) -> str:
    """Mention provenance for the scorer's prior -- structured header vs prose."""
    return "email_header" if group["from_structured"] else "text"


def _is_meaningful_name(normalized_value: str) -> bool:
    """Reject header 'names' that are only whitespace/punctuation (a parser artefact)."""
    return any(ch.isalnum() for ch in normalized_value)


def _mention_scoring_input(
    group: dict,
    *,
    name_df: int,
    selector_values: frozenset[str],
    neighbour_ids: frozenset[str] = frozenset(),
    attributes: dict[str, str] | None = None,
) -> MentionScoringInput:
    """Build the scorer input for one unresolved name group (pure)."""
    name = _pick_display_name(group["surface_texts"])
    return MentionScoringInput(
        name=name,
        normalized_name=group["normalized_value"],
        entity_type=group["entity_type"],
        provenance=_provenance_for_group(group),
        selector_values=selector_values,
        neighbor_entity_ids=neighbour_ids,
        attributes=attributes or {},
        name_df=max(1, name_df),
    )


def _plan(group: dict, scored: list[ScoredCandidate], config: EntityResolutionConfig) -> str:
    """Given decided candidates, what the sweep does: auto | review | provisional | left."""
    live = sorted((s for s in scored if not s.vetoed), key=lambda s: s.score, reverse=True)
    if live and live[0].band is ResolutionBand.AUTO:
        return "auto"
    if any(s.band is ResolutionBand.REVIEW for s in live):
        return "review"
    trustworthy = group["from_structured"] or len(group["mention_ids"]) >= config.min_mentions
    if group["entity_type"] is not None and config.create_provisional and trustworthy:
        return "provisional"
    return "left"


async def _entity_name_frequency(session: AsyncSession, dataset_id: str, *, cross_dataset: bool) -> dict[str, int]:
    """`display_name_normalized -> entity count` for the scorer's term-frequency adjustment."""
    stmt = select(EntityTable.display_name_normalized, func.count()).where(EntityTable.entity_type.in_(_NAME_TYPES))
    if not cross_dataset:
        stmt = stmt.where((EntityTable.dataset_id == dataset_id) | (EntityTable.dataset_id.is_(None)))
    stmt = stmt.group_by(EntityTable.display_name_normalized)
    return {name: n for name, n in (await session.execute(stmt)).all()}


async def _colocated_selector_values(session: AsyncSession, dataset_id: str) -> dict[str, set[str]]:
    """`name normalized_value -> {selector values it sits next to in a header}` (one query)."""
    nm = MentionTable.__table__.alias("nm")
    sm = MentionTable.__table__.alias("sm")
    stmt = (
        select(nm.c.normalized_value, sm.c.normalized_value)
        .select_from(
            nm.join(
                sm,
                (sm.c.file_id == nm.c.file_id)
                & (sm.c.field_path == nm.c.field_path)
                & (sm.c.dataset_id == nm.c.dataset_id),
            )
        )
        .where(
            nm.c.dataset_id == dataset_id,
            nm.c.entity_attribute == "name",
            nm.c.entity_id.is_(None),
            nm.c.field_path.is_not(None),
            sm.c.entity_type == EntityType.SELECTOR,
            sm.c.normalized_value.is_not(None),
        )
        .distinct()
    )
    out: dict[str, set[str]] = {}
    for name_nv, sel_nv in (await session.execute(stmt)).all():
        out.setdefault(name_nv, set()).add(sel_nv)
    return out


async def _groups_with_key_signal(session: AsyncSession, groups: list[dict]) -> set[str]:
    """Normalized values whose name shares at least one `entity_name_key` with an entity.

    Computes each group's keys (pure CPU) and does one existence query, so a
    group with no key hit can skip candidate generation entirely.
    """
    pairs_by_nv: dict[str, set[tuple[str, str]]] = {}
    all_keys: set[str] = set()
    for group in groups:
        keys = entity_keys(_pick_display_name(group["surface_texts"]))
        pairs_by_nv[group["normalized_value"]] = keys
        all_keys |= {k for _, k in keys}
    if not all_keys:
        return set()

    # Probe by the `key` string alone (a flat single-column IN scales; a composite
    # (key_type, key) IN of thousands of tuples blows Postgres' stack). Intersect
    # the full pair back in Python.
    keys = list(all_keys)
    hit: set[tuple[str, str]] = set()
    for start in range(0, len(keys), _KEY_PROBE_CHUNK):
        rows = (
            await session.execute(
                select(EntityNameKeyTable.key_type, EntityNameKeyTable.key)
                .where(EntityNameKeyTable.key.in_(keys[start : start + _KEY_PROBE_CHUNK]))
                .distinct()
            )
        ).all()
        hit |= {(kt, k) for kt, k in rows}
    return {nv for nv, group_pairs in pairs_by_nv.items() if group_pairs & hit}


_EMPLOYER_RELS = (RelationshipType.EMPLOYED_BY, RelationshipType.MEMBER_OF)
_NEIGHBOUR_EXCLUDE = frozenset({RelationshipType.APPEARS_IN_PHOTO_WITH, RelationshipType.CO_MENTION_OF})


class _CandDetail(NamedTuple):
    aliases: tuple[str, ...]
    selector_values: frozenset[str]
    neighbour_ids: frozenset[str]
    attributes: dict[str, str]


async def _candidate_details(session: AsyncSession, entity_ids: list[str]) -> dict[str, _CandDetail]:
    """`entity_id -> (aliases, has_selector values, graph neighbours, {employer})` for scored candidates."""
    if not entity_ids:
        return {}
    alias_rows = (
        await session.execute(select(EntityTable.id, EntityTable.aliases).where(EntityTable.id.in_(entity_ids)))
    ).all()
    aliases = {eid: tuple(a or ()) for eid, a in alias_rows}

    sel_rows = (
        await session.execute(
            select(EntityRelationshipTable.src_entity_id, SelectorTable.normalized_value)
            .join(SelectorTable, SelectorTable.entity_id == EntityRelationshipTable.dst_entity_id)
            .where(
                EntityRelationshipTable.src_entity_id.in_(entity_ids),
                EntityRelationshipTable.relationship_type == RelationshipType.HAS_SELECTOR,
            )
        )
    ).all()
    selectors: dict[str, set[str]] = {}
    for eid, value in sel_rows:
        selectors.setdefault(eid, set()).add(value)

    # graph neighbours (for co_mention_prior) + employer org (for attribute_agreement)
    edge_rows = (
        await session.execute(
            select(
                EntityRelationshipTable.src_entity_id,
                EntityRelationshipTable.dst_entity_id,
                EntityRelationshipTable.relationship_type,
            ).where(
                EntityRelationshipTable.src_entity_id.in_(entity_ids)
                | EntityRelationshipTable.dst_entity_id.in_(entity_ids)
            )
        )
    ).all()
    neighbours: dict[str, set[str]] = {}
    employer: dict[str, str] = {}
    ids = set(entity_ids)
    for src, dst, rel in edge_rows:
        if rel in _NEIGHBOUR_EXCLUDE:
            continue
        if src in ids:
            neighbours.setdefault(src, set()).add(dst)
            if rel in _EMPLOYER_RELS:
                employer.setdefault(src, dst)
        if dst in ids:
            neighbours.setdefault(dst, set()).add(src)

    return {
        eid: _CandDetail(
            aliases=aliases.get(eid, ()),
            selector_values=frozenset(selectors.get(eid, set())),
            neighbour_ids=frozenset(neighbours.get(eid, set())),
            attributes={"employer": employer[eid]} if eid in employer else {},
        )
        for eid in entity_ids
    }


_NEIGHBOUR_SAMPLE = 50


async def _group_neighbours(session: AsyncSession, mention_ids: list[str]) -> frozenset[str]:
    """Resolved name-entity ids co-mentioned in the same files as this name group.

    Samples the group's first `_NEIGHBOUR_SAMPLE` mentions: at most 50 neighbours are
    kept anyway, and joining every file of a 3,000-mention name took ~400 ms a group.
    """
    if not mention_ids:
        return frozenset()
    mention_ids = mention_ids[:_NEIGHBOUR_SAMPLE]
    m1 = MentionTable.__table__.alias("m1")
    m2 = MentionTable.__table__.alias("m2")
    rows = (
        await session.execute(
            select(m2.c.entity_id)
            .select_from(m1.join(m2, (m2.c.file_id == m1.c.file_id) & (m2.c.dataset_id == m1.c.dataset_id)))
            .where(
                m1.c.id.in_(mention_ids),
                m2.c.entity_id.is_not(None),
                m2.c.entity_attribute == "name",
            )
            .distinct()
            .limit(50)
        )
    ).all()
    return frozenset(eid for (eid,) in rows)


async def _group_employer(session: AsyncSession, mention_ids: list[str]) -> str | None:
    """The org an extractor tied this name to in a signature (`employed_by`/`member_of`), once resolved."""
    if not mention_ids:
        return None
    dst_mention = MentionTable.__table__.alias("dm")
    row = (
        await session.execute(
            select(dst_mention.c.entity_id)
            .select_from(
                MentionRelationshipTable.__table__.join(
                    dst_mention, dst_mention.c.id == MentionRelationshipTable.dst_mention_id
                )
            )
            .where(
                MentionRelationshipTable.src_mention_id.in_(mention_ids),
                MentionRelationshipTable.relationship_type.in_(_EMPLOYER_RELS),
                dst_mention.c.entity_id.is_not(None),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return row


async def _drop_provisional_if_canonical(
    session: AsyncSession, scored: list[ScoredCandidate], config: EntityResolutionConfig
) -> list[ScoredCandidate]:
    """Drop provisional-entity candidates when a canonical one is in play (review band or better).

    Otherwise the queue offers `E F Bolton (provisional)` beside `Edmond Bolton` for
    the same name -- that duplication belongs to `dedupe-entities`, not this card.
    A group whose only credible match is provisional keeps it.
    """
    ids = [s.entity_id for s in scored]
    canonical = set(
        (await session.execute(select(EntityTable.id).where(EntityTable.id.in_(ids), is_canonical_entity()))).scalars()
    )
    in_play = (ResolutionBand.AUTO, ResolutionBand.REVIEW)
    if len(canonical) == len(ids) or not any(
        s.entity_id in canonical and not s.vetoed and s.band in in_play for s in scored
    ):
        return scored
    kept = [s for s in scored if s.entity_id in canonical]
    decide(kept, config)
    return kept


async def _resolve_group(
    session: AsyncSession,
    group: dict,
    *,
    config: EntityResolutionConfig,
    name_df: int,
    selector_values: frozenset[str],
    has_key_signal: bool,
    entity_repo: PostgresEntityRepository,
    mention_repo: PostgresMentionRepository,
    ematch_repo: PostgresEntityMatchRepository,
    dataset_id: str,
) -> Counter:
    """Block -> score -> decide -> emit for one unresolved name group."""
    out: Counter = Counter()

    # Skip the candidate queries for a group with no signal at all -- no
    # `entity_name_key` hit, no header-colocated selector, no same-name entity.
    # (Most one-off newsletter senders in a large mailbox.)
    if not (has_key_signal or selector_values or name_df):
        mi = _mention_scoring_input(group, name_df=name_df, selector_values=selector_values)
        candidates = []
    else:
        neighbours = await _group_neighbours(session, group["mention_ids"])
        employer = await _group_employer(session, group["mention_ids"])
        mi = _mention_scoring_input(
            group,
            name_df=name_df,
            selector_values=selector_values,
            neighbour_ids=neighbours,
            attributes={"employer": employer} if employer else None,
        )
        candidates = await entity_repo.get_resolution_candidates(
            name=mi.name,
            dataset_id=dataset_id,
            entity_type=group["entity_type"],
            normalized_value=group["normalized_value"],
            selector_values=list(selector_values) or None,
            cross_dataset=config.cross_dataset,
            limit=config.candidate_limit,
        )

    scored: list[ScoredCandidate] = []
    if candidates:
        detail = await _candidate_details(session, [c.entity.id for c in candidates])
        for c in candidates:
            d = detail.get(c.entity.id)
            ci = CandidateScoringInput(
                entity_id=c.entity.id,
                entity_type=c.entity.entity_type,
                display_name=c.entity.display_name,
                aliases=d.aliases if d else (),
                selector_values=d.selector_values if d else frozenset(),
                neighbor_entity_ids=d.neighbour_ids if d else frozenset(),
                attributes=d.attributes if d else {},
                trigram_score=c.trigram_score,
                blocked_by=tuple(c.blocked_by),
            )
            scored.append(score_candidate(mi, ci, config))
        decide(scored, config)
        scored = await _drop_provisional_if_canonical(session, scored, config)

    plan = _plan(group, scored, config)
    live = sorted((s for s in scored if not s.vetoed), key=lambda s: s.score, reverse=True)
    runner_up = live[1].score if len(live) > 1 else None

    # Drop stale group rows a prior run wrote but this run no longer proposes --
    # only worth a query when we actually evaluated candidates this pass (a
    # no-signal group never had rows). `keep` = the entities we're writing now.
    async def _prune(keep: set[str]) -> None:
        if scored:
            await ematch_repo.prune_name_group_pending(
                dataset_id=dataset_id, normalized_value=group["normalized_value"], keep_entity_ids=keep
            )

    if plan == "auto":
        top = live[0]
        out["mentions_attached"] += await mention_repo.attach_many(group["mention_ids"], top.entity_id)
        await ematch_repo.create_name_group_match(
            _group_match(group, top, dataset_id=dataset_id, considered=len(live), runner_up=runner_up, config=config),
            confirmed=True,
        )
        await _prune({top.entity_id})
        out["names_auto_resolved"] += 1
    elif plan == "review":
        proposed = [s for s in live if s.band is ResolutionBand.REVIEW][:_REVIEW_ROWS_PER_GROUP]
        for sc in proposed:
            await ematch_repo.create_name_group_match(
                _group_match(group, sc, dataset_id=dataset_id, considered=len(live), runner_up=runner_up, config=config)
            )
        await _prune({s.entity_id for s in proposed})
        out["names_in_review"] += 1
    elif plan == "provisional":
        entity = await entity_repo.create_entity(
            EntityCreate(
                dataset_id=dataset_id,
                entity_type=group["entity_type"],
                display_name=mi.name,
                source=EntitySource.EXTRACTION,
            )
        )
        out["mentions_attached"] += await mention_repo.attach_many(group["mention_ids"], entity.id)
        await _prune(set())
        out["entities_created"] += 1
    else:
        await _prune(set())
        out["names_left_for_review"] += 1

    return out


def _group_match(
    group: dict,
    sc: ScoredCandidate,
    *,
    dataset_id: str,
    considered: int,
    runner_up: float | None,
    config: EntityResolutionConfig,
) -> EntityMatchCreate:
    return EntityMatchCreate(
        dataset_id=dataset_id,
        entity_id=sc.entity_id,
        mention_id=None,
        normalized_value=group["normalized_value"],
        mention_count=len(group["mention_ids"]),
        similarity_score=sc.score,
        match_method=sc.match_method,
        explanation=build_explanation(sc, candidates_considered=considered, runner_up_score=runner_up, config=config),
    )


_RECONCILE_SQL = """
WITH winner AS (
    SELECT DISTINCT ON (normalized_value) normalized_value, entity_id
    FROM mention
    WHERE dataset_id = :ds AND entity_attribute = 'name'
      AND entity_id IS NOT NULL AND normalized_value IS NOT NULL
    GROUP BY normalized_value, entity_id
    ORDER BY normalized_value, count(*) DESC
),
still_open AS (
    SELECT DISTINCT normalized_value FROM mention
    WHERE dataset_id = :ds AND entity_attribute = 'name'
      AND entity_id IS NULL AND normalized_value IS NOT NULL
)
UPDATE entity_match em
SET status = CASE WHEN em.entity_id = w.entity_id THEN 'CONFIRMED' ELSE 'REJECTED' END,
    reviewed_at = now(),
    decision_source = 'reconcile',
    explanation = CASE
        WHEN em.entity_id = w.entity_id AND em.explanation IS NOT NULL
        THEN jsonb_set(em.explanation, '{band}', '"auto"')
        ELSE em.explanation
    END
FROM winner w
WHERE em.dataset_id = :ds AND em.mention_id IS NULL AND em.normalized_value IS NOT NULL
  AND em.status = 'PENDING' AND em.reviewed_by IS NULL
  AND em.normalized_value = w.normalized_value
  AND em.normalized_value NOT IN (SELECT normalized_value FROM still_open)
"""


async def _reconcile_resolved_name_groups(session: AsyncSession, dataset_id: str) -> int:
    """Close group-level `entity_match` rows whose name group is now fully resolved.

    A name that auto-resolved in an earlier pass no longer appears in
    `unresolved_name_groups`, so a stale `pending` row for it never gets
    revisited. This marks the row `confirmed` if it points at the entity the
    mentions actually resolved to, else `rejected`. Analyst decisions untouched.
    """
    result = await session.execute(text(_RECONCILE_SQL), {"ds": dataset_id})
    await session.commit()
    return result.rowcount or 0


_APPLY_CONFIRMED_SQL = """
WITH decided AS (
    SELECT em.normalized_value, e.entity_type, min(em.entity_id) AS entity_id
    FROM entity_match em JOIN entity e ON e.id = em.entity_id
    WHERE em.dataset_id = :ds AND em.mention_id IS NULL AND em.provisional_entity_id IS NULL
      AND em.normalized_value IS NOT NULL AND em.status = 'CONFIRMED'
    GROUP BY em.normalized_value, e.entity_type
    HAVING count(DISTINCT em.entity_id) = 1
)
UPDATE mention m
SET entity_id = d.entity_id
FROM decided d
WHERE m.dataset_id = :ds AND m.entity_id IS NULL AND m.entity_attribute = 'name'
  AND m.normalized_value = d.normalized_value
  AND (m.entity_type IS NULL OR m.entity_type = d.entity_type)
"""


async def _apply_confirmed_name_groups(session: AsyncSession, dataset_id: str) -> int:
    """Attach unresolved name mentions to the entity their name group was already confirmed to.

    Group-level decisions are keyed by name, not mention, so they outlive a
    re-extraction (`reset-entities` / a new extractor run) -- without this the
    fresh mentions would sit unresolved, or be re-queued, despite an analyst
    (or an earlier auto pass) having already decided them. A name confirmed to
    more than one same-typed entity is ambiguous and left to normal scoring.
    """
    result = await session.execute(text(_APPLY_CONFIRMED_SQL), {"ds": dataset_id})
    await session.commit()
    return result.rowcount or 0


async def _resolve_group_isolated(engine, group: dict, **kw) -> Counter:
    """Run `_resolve_group` on its own `AsyncSession` (for the concurrent path).

    A failed group is logged and skipped -- it just stays unresolved and a re-run
    retries it -- rather than aborting the whole sweep.
    """
    try:
        async with AsyncSession(engine, expire_on_commit=False) as s:
            return await _resolve_group(
                s,
                group,
                entity_repo=PostgresEntityRepository(session=s),
                mention_repo=PostgresMentionRepository(session=s),
                ematch_repo=PostgresEntityMatchRepository(session=s),
                **kw,
            )
    except Exception as exc:  # noqa: BLE001 -- one bad group shouldn't fail the sweep
        logger.warning(f"resolve group {group['normalized_value']!r} failed: {exc}")
        return Counter()


async def resolve_entities_workflow(
    session: AsyncSession,
    dataset_id: str,
    *,
    config: EntityResolutionConfig | None = None,
    min_mentions: int | None = None,
    create: bool | None = None,
    link_selectors: bool = True,
    concurrency: int = 1,
) -> dict[str, int]:
    """Resolve a dataset's unresolved name mentions. Returns per-outcome counts.

    `concurrency > 1` scores groups in parallel, each on its own session/
    connection -- an ~Nx speedup on a large mailbox (the loop is I/O-bound).
    """
    config = config or DEFAULT_RESOLUTION_CONFIG
    if min_mentions is not None or create is not None:
        config = config.model_copy(
            update={
                "min_mentions": min_mentions if min_mentions is not None else config.min_mentions,
                "create_provisional": create if create is not None else config.create_provisional,
            }
        )

    mention_repo = PostgresMentionRepository(session=session)
    entity_repo = PostgresEntityRepository(session=session)
    ematch_repo = PostgresEntityMatchRepository(session=session)

    decisions_applied = await _apply_confirmed_name_groups(session, dataset_id)
    groups = [
        g
        for g in await mention_repo.unresolved_name_groups(dataset_id=dataset_id, entity_types=_NAME_TYPES)
        if _is_meaningful_name(g["normalized_value"])
    ]
    name_df = await _entity_name_frequency(session, dataset_id, cross_dataset=config.cross_dataset)
    colocated = await _colocated_selector_values(session, dataset_id)
    key_signal = await _groups_with_key_signal(session, groups)

    def _kw(group: dict) -> dict:
        nv = group["normalized_value"]
        return {
            "config": config,
            "name_df": name_df.get(nv, 0),
            "selector_values": frozenset(colocated.get(nv, set())),
            "has_key_signal": nv in key_signal,
            "dataset_id": dataset_id,
        }

    totals: Counter = Counter()
    if concurrency > 1:
        engine = session.bind
        sem = asyncio.Semaphore(concurrency)

        async def _one(group: dict) -> Counter:
            async with sem:
                return await _resolve_group_isolated(engine, group, **_kw(group))

        for result in await asyncio.gather(*(_one(g) for g in tqdm(groups, desc="Resolving names", unit=" name"))):
            totals += result
    else:
        for group in tqdm(groups, desc="Resolving names", unit=" name"):
            totals += await _resolve_group(
                session,
                group,
                entity_repo=entity_repo,
                mention_repo=mention_repo,
                ematch_repo=ematch_repo,
                **_kw(group),
            )

    edges = await PostgresGraphRepository(session=session).link_header_selectors(dataset_id) if link_selectors else 0
    candidates = await PostgresMentionRelationshipRepository(session=session).promote_to_candidates(dataset_id)
    closed = await _reconcile_resolved_name_groups(session, dataset_id)

    counts = {
        "decisions_applied": decisions_applied,
        "names_auto_resolved": totals["names_auto_resolved"],
        "names_in_review": totals["names_in_review"],
        "entities_created": totals["entities_created"],
        "mentions_attached": totals["mentions_attached"],
        "names_left_for_review": totals["names_left_for_review"],
        "review_rows_closed": closed,
        "has_selector_edges": edges,
        "relationship_candidates": candidates,
    }
    logger.success(f"Resolved entities for dataset {dataset_id}: {counts}")
    return counts
