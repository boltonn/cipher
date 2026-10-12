"""Entity resolution, match + decide: unresolved name mentions -> entities, one unit at a time.

A **unit** is one name key (`normalize_name`) -- every unresolved name mention with it, of any
type, plus the person/organization entities whose display name has it. Steps
(`resolve_entities_workflow`; the stage around it is `resolution.resolution_workflow`):

1. **Same names** (`_settle_same_names`) -- auto-created entities of the keeper's type fold into
   it; the unit's names attach to an auto-created keeper when their type agrees; same name /
   other type becomes a merge suggestion. A verified entity is never assumed from its name.
2. **Match names** (`_resolve_group`) -- block candidates (`get_resolution_candidates`: selector,
   exact name, `entity_name_key`, trigram), score them (Fellegi-Sunter, `entity_resolution`),
   then `decide()`: attach on the one safe rule (exact header identifier + name), a pending
   group-level `entity_match` per review-band candidate, or -- nothing matched -- one
   auto-created entity for a trustworthy typed unit.
3. **Match new entities** (`_score_entity_unit`) -- auto-created entities new since the last run
   against other entities: merge suggestions for the review band, on the smaller side.

Re-runnable: reads only `entity_id IS NULL` mentions and upserts suggestions without touching
analyst decisions. `reset-entities` clears it all. Design: `docs/entity-resolution.md` §0.
"""

import asyncio
from collections import Counter
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import NamedTuple

from loguru import logger
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.repositories import (
    PostgresEntityMatchRepository,
    PostgresEntityRepository,
    PostgresMentionRepository,
)
from cipher.datastores.postgres.repositories._merge import fold_entity
from cipher.datastores.postgres.tables.entity import EntityTable, is_canonical_entity
from cipher.datastores.postgres.tables.entity_match import EntityMatchTable
from cipher.datastores.postgres.tables.entity_name_key import EntityNameKeyTable
from cipher.datastores.postgres.tables.entity_relationship import EntityRelationshipTable
from cipher.datastores.postgres.tables.mention import MentionTable
from cipher.datastores.postgres.tables.mention_relationship import MentionRelationshipTable
from cipher.datastores.postgres.tables.person import PersonTable
from cipher.datastores.postgres.tables.selector import SelectorTable
from cipher.datastores.postgres.utils import normalize_name
from cipher.names import entity_keys, fold, parse_name, share_nickname_root, to_latin
from cipher.orchestration.entity_resolution import (
    CandidateScoringInput,
    MentionScoringInput,
    ScoredCandidate,
    build_explanation,
    decide,
    dominant_method,
    score_candidate,
)
from cipher.schemas.graph.entity import EntityCreate
from cipher.schemas.graph.entity_match import EntityMatchCreate, EntityMatchMethod, EntityMatchStatus
from cipher.schemas.graph.entity_resolution import (
    DEFAULT_RESOLUTION_CONFIG,
    EntityResolutionConfig,
    FeatureLevel,
    ResolutionBand,
    ResolutionExplanation,
    ResolutionFeature,
)
from cipher.schemas.graph.mention import MentionedType
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
    surname_words: frozenset[str] = frozenset(),
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
        surname_words=surname_words,
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
                & (sm.c.mentioned_id == nm.c.mentioned_id)
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

    # DOB / nationality: the person record, then what records already attached to the entity assert.
    record_attrs = await _record_attributes(session, lambda nm: nm.c.entity_id.in_(entity_ids))
    dob_rows = (
        await session.execute(
            select(EntityTable.id, PersonTable.date_of_birth)
            .join(PersonTable, PersonTable.id == EntityTable.person_id)
            .where(EntityTable.id.in_(entity_ids), PersonTable.date_of_birth.is_not(None))
        )
    ).all()
    dob = {eid: value.date().isoformat() for eid, value in dob_rows}

    def attributes(eid: str) -> dict[str, str]:
        out = _settled(record_attrs.get(eid))
        if eid in dob:
            out["date_of_birth"] = dob[eid]
        if eid in employer:
            out["employer"] = employer[eid]
        return out

    return {
        eid: _CandDetail(
            aliases=aliases.get(eid, ()),
            selector_values=frozenset(selectors.get(eid, set())),
            neighbour_ids=frozenset(neighbours.get(eid, set())),
            attributes=attributes(eid),
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


_RECORD_ATTRIBUTES = ("date_of_birth", "nationality")


async def _record_attributes(session: AsyncSession, name_mention_filter) -> dict[str, dict[str, Counter]]:  # noqa: ANN001
    """DOB / nationality asserted in the same structured record as some name mentions (a table row, a contact).

    `name_mention_filter` selects the name mentions; their record is `(file_id, mentioned_id, field_path)`.
    Returns `key -> attribute -> Counter(value)`, where key is the name mention's `entity_id` or `id`.
    """
    names = MentionTable.__table__.alias("nm")
    attrs = MentionTable.__table__.alias("am")
    rows = await session.execute(
        select(func.coalesce(names.c.entity_id, names.c.id), attrs.c.entity_attribute, attrs.c.normalized_value)
        .select_from(
            names.join(
                attrs,
                (attrs.c.file_id == names.c.file_id)
                & (attrs.c.mentioned_id == names.c.mentioned_id)
                & (attrs.c.field_path == names.c.field_path),
            )
        )
        .where(
            name_mention_filter(names),
            names.c.mentioned_type == MentionedType.STRUCTURED_FIELD,
            attrs.c.entity_attribute.in_(_RECORD_ATTRIBUTES),
            attrs.c.normalized_value.is_not(None),
        )
    )
    out: dict[str, dict[str, Counter]] = {}
    for key, attribute, value in rows.all():
        out.setdefault(key, {}).setdefault(attribute, Counter())[value] += 1
    return out


def _settled(values: dict[str, Counter] | None) -> dict[str, str]:
    """One value per attribute, only when the evidence agrees (two DOBs on one name group decide nothing)."""
    return {attr: next(iter(counter)) for attr, counter in (values or {}).items() if len(counter) == 1}


async def _group_attributes(session: AsyncSession, mention_ids: list[str]) -> dict[str, str]:
    """The DOB / nationality this name group's own records assert, if consistent."""
    if not mention_ids:
        return {}
    found = await _record_attributes(session, lambda nm: nm.c.id.in_(mention_ids))
    merged: dict[str, Counter] = {}
    for per_mention in found.values():
        for attr, counter in per_mention.items():
            merged.setdefault(attr, Counter()).update(counter)
    return _settled(merged)


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
    surname_words: frozenset[str] = frozenset(),
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
        mi = _mention_scoring_input(
            group, name_df=name_df, selector_values=selector_values, surname_words=surname_words
        )
        candidates = []
    else:
        neighbours = await _group_neighbours(session, group["mention_ids"])
        employer = await _group_employer(session, group["mention_ids"])
        attributes = await _group_attributes(session, group["mention_ids"])
        if employer:
            attributes["employer"] = employer
        mi = _mention_scoring_input(
            group,
            name_df=name_df,
            selector_values=selector_values,
            neighbour_ids=neighbours,
            attributes=attributes or None,
            surname_words=surname_words,
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


async def reconcile_resolved_name_groups(session: AsyncSession, dataset_id: str) -> int:
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


# `(step, done, total)` as a step advances -- the run's live progress
StepReporter = Callable[[str, int, int], Awaitable[None]]


async def _no_report(step: str, done: int, total: int) -> None:
    return None


class _EntityRow(NamedTuple):
    id: str
    entity_type: EntityType
    display_name: str
    key: str
    is_canonical: bool
    mentions: int
    date_created: datetime


async def _entity_units(session: AsyncSession, dataset_id: str) -> dict[str, list[_EntityRow]]:
    """`name key -> person/organization entities whose display name has it` (with mention counts)."""
    counts = (
        select(MentionTable.entity_id, func.count().label("n"))
        .where(MentionTable.dataset_id == dataset_id, MentionTable.entity_id.is_not(None))
        .group_by(MentionTable.entity_id)
        .subquery()
    )
    rows = await session.execute(
        select(
            EntityTable.id,
            EntityTable.entity_type,
            EntityTable.display_name,
            EntityTable.display_name_normalized,
            is_canonical_entity().label("canonical"),
            func.coalesce(counts.c.n, 0).label("n"),
            EntityTable.date_created,
        )
        .outerjoin(counts, counts.c.entity_id == EntityTable.id)
        .where(EntityTable.dataset_id == dataset_id, EntityTable.entity_type.in_(_NAME_TYPES))
    )
    units: dict[str, list[_EntityRow]] = {}
    for r in rows:
        units.setdefault(r.display_name_normalized, []).append(
            _EntityRow(
                r.id, r.entity_type, r.display_name, r.display_name_normalized, bool(r.canonical), r.n, r.date_created
            )
        )
    return units


def _surname_words(names: list[str]) -> frozenset[str]:
    """Words this dataset's full person names use as surnames far more than as given names.

    A lone `Bolton` is then compared as a surname (`compare_names(surname_words=)`): seen as a
    surname at least 3 times and at least 3x as often as a given name.
    """
    as_surname: Counter = Counter()
    as_given: Counter = Counter()
    for name in names:
        parsed = parse_name(name)
        if parsed.given and parsed.primary_surname:
            as_surname[fold(to_latin(parsed.primary_surname))] += 1
            as_given[fold(to_latin(parsed.given_primary))] += 1
    return frozenset(w for w, n in as_surname.items() if n >= 3 and n >= 3 * as_given[w])


def _keeper(rows: list[_EntityRow]) -> _EntityRow:
    """The entity a unit settles on: a verified one first, then the one with most mentions."""
    return max(rows, key=lambda r: (r.is_canonical, r.mentions))


def _same_name_explanation(detail: str) -> dict:
    return ResolutionExplanation(
        score=0.99,
        band=ResolutionBand.REVIEW,
        features=[
            ResolutionFeature(name="name_exact", level=FeatureLevel.EXACT, weight=0.0, contribution=0.0, detail=detail)
        ],
    ).model_dump(mode="json")


async def _settle_same_names(
    session: AsyncSession,
    *,
    dataset_id: str,
    entity_units: dict[str, list[_EntityRow]],
    groups_by_key: dict[str, dict],
    report: StepReporter,
) -> Counter:
    """Decide what one name already settles, before any scoring.

    An auto-created entity is defined by its name -- nobody has said otherwise -- so in a unit
    (one name key) auto-created entities of the keeper's type fold into it, and the unit's
    unresolved names attach to an auto-created keeper when their type agrees. A verified
    entity is defined by its identity, so its same-name mentions are scored, never assumed.
    Same name but another type (`Adaire` the person vs the organization) is asked on the card.
    """
    out: Counter = Counter()
    mention_repo = PostgresMentionRepository(session=session)
    ematch_repo = PostgresEntityMatchRepository(session=session)
    total = len(entity_units)
    for done, (key, rows) in enumerate(entity_units.items(), start=1):
        keeper = _keeper(rows)
        # one head per type: the keeper for its own type, else that type's biggest entity
        heads: dict[EntityType, _EntityRow] = {}
        for entity_type in dict.fromkeys(r.entity_type for r in rows):
            same = [r for r in rows if r.entity_type == entity_type]
            head = keeper if entity_type == keeper.entity_type else _keeper(same)
            heads[entity_type] = head
            for row in same:
                if row is not head and not row.is_canonical:
                    await fold_entity(session, source_id=row.id, target_id=head.id)
                    out["entities_folded"] += 1
        apart = [head for head in heads.values() if head is not keeper]
        for row in apart:
            await ematch_repo.create_merge_match(
                EntityMatchCreate(
                    dataset_id=dataset_id,
                    entity_id=keeper.id,
                    provisional_entity_id=row.id,
                    similarity_score=0.99,
                    match_method=EntityMatchMethod.NAME_EXACT,
                    explanation=_same_name_explanation(
                        f"same name, {row.entity_type.value} vs {keeper.entity_type.value}"
                    ),
                )
            )
            out["same_name_proposed"] += 1
        group = groups_by_key.get(key)
        # names attach to the auto-created entity of their own type; untyped ones only when one type is in play
        target = heads.get(group["entity_type"]) if group and group["entity_type"] else (keeper if not apart else None)
        if group and target is not None and not target.is_canonical:
            out["mentions_attached"] += await mention_repo.attach_many(group["mention_ids"], target.id)
            out["names_attached"] += 1
            del groups_by_key[key]
        entity_units[key] = [keeper, *apart]
        if done % 200 == 0 or done == total:
            await session.commit()
            await report("same_names", done, total)
    return out


_SHORT_NAME_SQL = """
WITH short AS (
    SELECT m.id, m.file_id, m.surface_text, m.normalized_value, m.entity_id
    FROM mention m
    LEFT JOIN entity e ON e.id = m.entity_id
    WHERE m.dataset_id = :ds AND m.entity_attribute = 'name' AND m.file_id IS NOT NULL
      AND (m.entity_type IS NULL OR m.entity_type = 'PERSON')
      AND position(' ' IN m.normalized_value) = 0 AND length(m.normalized_value) > 1
      AND (m.entity_id IS NULL OR (
            e.entity_type = 'PERSON' AND e.person_id IS NULL AND e.location_id IS NULL
            AND e.source <> 'MANUAL' AND position(' ' IN e.display_name_normalized) = 0))
),
fuller AS (
    SELECT DISTINCT m.file_id, m.surface_text, m.entity_id
    FROM mention m JOIN entity e ON e.id = m.entity_id
    WHERE m.dataset_id = :ds AND m.entity_attribute = 'name' AND e.entity_type = 'PERSON'
      AND position(' ' IN m.normalized_value) > 0
      AND m.file_id IN (SELECT file_id FROM short)
)
SELECT 'short' AS kind, id, file_id, surface_text, entity_id FROM short
UNION ALL
SELECT 'fuller', NULL, file_id, surface_text, entity_id FROM fuller
"""


def _short_name_refers_to(short: str, fuller: str) -> bool:
    """Can `Nick` / `Mr. Bolton` / `Bolton` be this fuller name? First name, nickname or surname."""
    s, f = parse_name(short), parse_name(fuller)
    word = fold(to_latin((s.given or s.surnames or ("",))[0]))
    titled = bool(set(s.prefixes) & {"mr", "mrs", "ms", "miss", "dr", "prof"})
    surname = fold(to_latin(f.primary_surname)) if f.primary_surname else ""
    given = fold(to_latin(f.given_primary)) if f.given_primary else ""
    if not word:
        return False
    if word == surname:
        return True
    return not titled and bool(given) and (word == given or share_nickname_root(word, b=given))


async def _resolve_short_names(session: AsyncSession, dataset_id: str) -> Counter:
    """Within-document coreference: `Nick` in an email that also names `Nick Bolton` is that Nick Bolton.

    A one-word person mention (or `Mr. Bolton`) -- unresolved, or sitting on a one-word
    auto-created person -- takes the entity of the one fuller, resolved person name in the
    same file it can stand for. Two candidates (`Nick Bolton`, `Nick Jones`) decide nothing.
    Auto-created entities emptied this way are dropped.
    """
    out: Counter = Counter()
    rows = (await session.execute(text(_SHORT_NAME_SQL), {"ds": dataset_id})).all()
    fuller: dict[str, list[tuple[str, str]]] = {}
    for row in rows:
        if row.kind == "fuller":
            fuller.setdefault(row.file_id, []).append((row.surface_text, row.entity_id))
    moves: dict[str, list[str]] = {}
    for row in rows:
        if row.kind != "short" or row.file_id not in fuller:
            continue
        targets = {eid for surface, eid in fuller[row.file_id] if _short_name_refers_to(row.surface_text, surface)}
        if len(targets) == 1 and (target := targets.pop()) != row.entity_id:
            moves.setdefault(target, []).append(row.id)
    for target, mention_ids in moves.items():
        for start in range(0, len(mention_ids), 5000):
            await session.execute(
                update(MentionTable)
                .where(MentionTable.id.in_(mention_ids[start : start + 5000]))
                .values(entity_id=target)
            )
        out["mentions_attached"] += len(mention_ids)
    out["entities_emptied"] = await PostgresEntityRepository(session=session).delete_empty_provisional(dataset_id)
    await session.commit()
    return out


async def _entity_weights(session: AsyncSession, entity_ids: list[str]) -> dict[str, tuple[bool, int]]:
    """`entity_id -> (verified, mention count)`: which side of a merge survives."""
    mentions = select(func.count()).select_from(MentionTable).where(MentionTable.entity_id == EntityTable.id)
    rows = await session.execute(
        select(EntityTable.id, is_canonical_entity(), mentions.scalar_subquery()).where(EntityTable.id.in_(entity_ids))
    )
    return {eid: (bool(canonical), n) for eid, canonical, n in rows}


async def _score_entity_unit(
    session: AsyncSession,
    row: _EntityRow,
    *,
    config: EntityResolutionConfig,
    name_df: int,
    dataset_id: str,
    surname_words: frozenset[str] = frozenset(),
) -> Counter:
    """Score an auto-created entity against other entities; file merge suggestions for the review band.

    The smaller, auto-created side is the one proposed to merge into the other.
    """
    out: Counter = Counter()
    entity_repo = PostgresEntityRepository(session=session)
    ematch_repo = PostgresEntityMatchRepository(session=session)
    candidates = [
        c
        for c in await entity_repo.get_resolution_candidates(
            name=row.display_name,
            dataset_id=dataset_id,
            entity_type=row.entity_type,
            cross_dataset=config.cross_dataset,
            limit=config.candidate_limit,
        )
        if c.entity.id != row.id and normalize_name(c.entity.display_name) != row.key
    ]
    proposed: set[str] = set()
    if candidates:
        own = (await _candidate_details(session, [row.id])).get(row.id)
        mention_ids = list(
            (
                await session.execute(
                    select(MentionTable.id).where(MentionTable.entity_id == row.id).limit(_NEIGHBOUR_SAMPLE)
                )
            ).scalars()
        )
        mi = MentionScoringInput(
            name=row.display_name,
            normalized_name=row.key,
            entity_type=row.entity_type,
            provenance="text",
            selector_values=own.selector_values if own else frozenset(),
            neighbor_entity_ids=(await _group_neighbours(session, mention_ids))
            | (own.neighbour_ids if own else frozenset()),
            attributes=own.attributes if own else {},
            name_df=max(1, name_df),
            surname_words=surname_words,
        )
        detail = await _candidate_details(session, [c.entity.id for c in candidates])
        scored = []
        for c in candidates:
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
            (s for s in scored if not s.vetoed and s.score >= config.review_low), key=lambda s: s.score, reverse=True
        )[:_REVIEW_ROWS_PER_GROUP]
        weights = await _entity_weights(session, [s.entity_id for s in live])
        runner_up = live[1].score if len(live) > 1 else None
        for sc in live:
            canonical, mentions = weights.get(sc.entity_id, (False, 0))
            row_survives = not canonical and mentions < row.mentions
            await ematch_repo.create_merge_match(
                EntityMatchCreate(
                    dataset_id=dataset_id,
                    entity_id=row.id if row_survives else sc.entity_id,
                    provisional_entity_id=sc.entity_id if row_survives else row.id,
                    similarity_score=sc.score,
                    match_method=dominant_method(sc),
                    explanation=build_explanation(
                        sc, candidates_considered=len(live), runner_up_score=runner_up, config=config
                    ),
                )
            )
            if not row_survives:
                proposed.add(sc.entity_id)
            out["merges_proposed"] += 1
    await ematch_repo.prune_merge_pending(dataset_id=dataset_id, provisional_entity_id=row.id, keep_entity_ids=proposed)
    return out


async def _isolated(engine, label: str, fn, *args, **kw) -> Counter:  # noqa: ANN001
    """Run one unit's work on its own session; a failure is logged and skipped (a re-run retries it)."""
    try:
        async with AsyncSession(engine, expire_on_commit=False) as s:
            return await fn(s, *args, **kw)
    except Exception as exc:  # noqa: BLE001 -- one bad unit shouldn't fail the sweep
        logger.warning(f"resolve {label!r} failed: {exc}")
        return Counter()


async def _run_units(
    session: AsyncSession, items: list, work, *, concurrency: int, step: str, report: StepReporter, label
) -> Counter:  # noqa: ANN001
    """`work(session, item)` for every item, `concurrency` at a time, reporting `step` progress."""
    totals: Counter = Counter()
    total, done = len(items), 0
    sem = asyncio.Semaphore(max(1, concurrency))

    async def _one(item) -> Counter:  # noqa: ANN001
        nonlocal done
        async with sem:
            result = await _isolated(session.bind, label(item), work, item)
        done += 1
        if done % 50 == 0 or done == total:
            await report(step, done, total)
        return result

    for result in await asyncio.gather(*(_one(item) for item in items)):
        totals += result
    if not items:
        await report(step, 0, 0)
    return totals


async def resolve_entities_workflow(
    session: AsyncSession,
    dataset_id: str,
    *,
    config: EntityResolutionConfig | None = None,
    min_mentions: int | None = None,
    create: bool | None = None,
    concurrency: int = 8,
    entities_since: datetime | None = None,
    report: StepReporter = _no_report,
) -> dict[str, int]:
    """Match and decide every resolution unit -- one name key -- of a dataset. Returns per-outcome counts.

    1. **Same names** (`_settle_same_names`): fold same-type auto-created duplicates, attach a
       unit's names to its auto-created entity, ask about same name / other type.
    2. **Names**: score each remaining unit's unresolved names against entities -- attach on the
       safe rule, suggest the review band, create one auto-created entity when nothing matched.
    3. **Entities**: score auto-created entities created after `entities_since` (all when None)
       against other entities -- merge suggestions for the review band.

    Units run `concurrency` at a time, each on its own session. Linking and the other derived
    steps are the caller's (`resolution.resolution_workflow`).
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

    # proposals from the retired `group-duplicates` pass; units now cover them
    await session.execute(
        delete(EntityMatchTable).where(
            EntityMatchTable.dataset_id == dataset_id,
            EntityMatchTable.status == EntityMatchStatus.PENDING,
            EntityMatchTable.explanation.has_key("group"),
        )
    )
    decisions_applied = await _apply_confirmed_name_groups(session, dataset_id)
    groups_by_key = {
        g["normalized_value"]: g
        for g in await mention_repo.unresolved_name_groups(dataset_id=dataset_id, entity_types=_NAME_TYPES)
        if _is_meaningful_name(g["normalized_value"])
    }
    entity_units = await _entity_units(session, dataset_id)
    settled = await _settle_same_names(
        session, dataset_id=dataset_id, entity_units=entity_units, groups_by_key=groups_by_key, report=report
    )

    groups = list(groups_by_key.values())
    surname_words = _surname_words(
        [
            *(_pick_display_name(g["surface_texts"]) for g in groups if g["entity_type"] != EntityType.ORGANIZATION),
            *(r.display_name for rows in entity_units.values() for r in rows if r.entity_type == EntityType.PERSON),
        ]
    )
    name_df = await _entity_name_frequency(session, dataset_id, cross_dataset=config.cross_dataset)
    colocated = await _colocated_selector_values(session, dataset_id)
    key_signal = await _groups_with_key_signal(session, groups)

    async def _score_names(s: AsyncSession, group: dict) -> Counter:
        nv = group["normalized_value"]
        return await _resolve_group(
            s,
            group,
            config=config,
            name_df=name_df.get(nv, 0),
            selector_values=frozenset(colocated.get(nv, set())),
            has_key_signal=nv in key_signal,
            surname_words=surname_words,
            entity_repo=PostgresEntityRepository(session=s),
            mention_repo=PostgresMentionRepository(session=s),
            ematch_repo=PostgresEntityMatchRepository(session=s),
            dataset_id=dataset_id,
        )

    names = await _run_units(
        session,
        groups,
        _score_names,
        concurrency=concurrency,
        step="names",
        report=report,
        label=lambda g: g["normalized_value"],
    )

    short = await _resolve_short_names(session, dataset_id)
    await report("short_names", 1, 1)
    entity_units = await _entity_units(session, dataset_id)  # short names may have emptied some

    keepers = {key: _keeper(rows) for key, rows in entity_units.items()}
    new_entities = [
        keeper
        for key, keeper in keepers.items()
        if key not in groups_by_key
        and not keeper.is_canonical
        and (entities_since is None or keeper.date_created > entities_since)
    ]

    async def _score_entity(s: AsyncSession, row: _EntityRow) -> Counter:
        return await _score_entity_unit(
            s,
            row,
            config=config,
            name_df=name_df.get(row.key, 0),
            dataset_id=dataset_id,
            surname_words=surname_words,
        )

    entities = await _run_units(
        session,
        new_entities,
        _score_entity,
        concurrency=concurrency,
        step="entities",
        report=report,
        label=lambda r: r.display_name,
    )

    counts = {
        "decisions_applied": decisions_applied,
        "units": len(set(groups_by_key) | set(entity_units)),
        "entities_folded": settled["entities_folded"],
        "names_attached_by_name": settled["names_attached"],
        "same_name_suggestions": settled["same_name_proposed"],
        "names_auto_resolved": names["names_auto_resolved"],
        "names_in_review": names["names_in_review"],
        "entities_created": names["entities_created"],
        "mentions_attached": settled["mentions_attached"] + names["mentions_attached"],
        "names_left_for_review": names["names_left_for_review"],
        "entities_scored": len(new_entities),
        "merge_suggestions": entities["merges_proposed"],
        "short_names_attached": short["mentions_attached"],
        "entities_emptied": short["entities_emptied"],
    }
    logger.success(f"Resolved entities for dataset {dataset_id}: {counts}")
    return counts
