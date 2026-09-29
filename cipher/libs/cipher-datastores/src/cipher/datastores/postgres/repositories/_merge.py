"""Shared logic for folding one entity id into another.

`PostgresPersonRepository.merge_persons` and `PostgresEntityRepository.merge_entities`
both need to move every row keyed on an entity id (a person's shared-id bridge
node counts) onto the surviving id, dropping rows that would self-reference or
duplicate one the survivor already has. That SQL -- especially the correlated
de-dupe for the two unique edge triples -- lives here so both callers stay in
sync.
"""

from sqlalchemy import and_, delete, literal, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.repositories.entity_name_key import refresh_entity_name_keys
from cipher.datastores.postgres.tables.comment import CommentTable
from cipher.datastores.postgres.tables.entity import EntityTable
from cipher.datastores.postgres.tables.entity_match import EntityMatchTable
from cipher.datastores.postgres.tables.entity_relationship import EntityRelationshipTable
from cipher.datastores.postgres.tables.entity_relationship_candidate import EntityRelationshipCandidateTable
from cipher.datastores.postgres.tables.event_participant import EventParticipantTable
from cipher.datastores.postgres.tables.mention import MentionTable
from cipher.datastores.postgres.tables.person import PersonTable
from cipher.schemas.graph.entity_match import EntityMatchStatus
from cipher.schemas.interaction.comment import CommentableType


async def _repoint_edge_table(session: AsyncSession, table, *, source_id: str, target_id: str) -> int:
    """Repoint a ``(src_entity_id, dst_entity_id, relationship_type)`` edge table.

    Moves rows off ``source_id`` onto ``target_id``, dropping self-loops and rows
    that would duplicate an edge ``target_id`` already has. Returns rows moved.
    """
    tbl = table.__table__
    await session.execute(
        delete(table).where(
            or_(
                and_(table.src_entity_id == source_id, table.dst_entity_id == target_id),
                and_(table.src_entity_id == target_id, table.dst_entity_id == source_id),
            )
        )
    )
    for own_col, other_col in (("src_entity_id", "dst_entity_id"), ("dst_entity_id", "src_entity_id")):
        existing = tbl.alias(f"existing_{own_col}")
        await session.execute(
            delete(table).where(
                getattr(table, own_col) == source_id,
                select(literal(1))
                .select_from(existing)
                .where(
                    existing.c[own_col] == target_id,
                    existing.c[other_col] == getattr(table, other_col),
                    existing.c.relationship_type == table.relationship_type,
                )
                .exists(),
            )
        )
    moved = 0
    for col in ("src_entity_id", "dst_entity_id"):
        moved += (
            await session.execute(update(table).where(getattr(table, col) == source_id).values({col: target_id}))
        ).rowcount or 0
    return moved


async def repoint_entity_references(session: AsyncSession, *, source_id: str, target_id: str) -> dict[str, int]:
    """Repoint every row keyed on an entity id from ``source_id`` onto ``target_id``.

    Covers ``mention``, ``entity_relationship``, ``entity_relationship_candidate``,
    ``entity_match``, ``event_participant`` and ``comment`` (person + entity
    threads). Does **not** touch the ``entity`` row itself or the person-only
    tables (``face``, ``face_match``) -- the caller owns those and the final
    delete. Runs inside the caller's transaction; does not commit. Returns
    per-table repointed counts.
    """
    mentions = (
        await session.execute(
            update(MentionTable).where(MentionTable.entity_id == source_id).values(entity_id=target_id)
        )
    ).rowcount or 0

    relationships = await _repoint_edge_table(
        session, EntityRelationshipTable, source_id=source_id, target_id=target_id
    )
    relationship_candidates = await _repoint_edge_table(
        session, EntityRelationshipCandidateTable, source_id=source_id, target_id=target_id
    )

    entity_matches = await _repoint_entity_matches(session, source_id=source_id, target_id=target_id)

    # event_participant: no uniqueness constraint, but avoid listing the survivor
    # on the same event twice.
    await session.execute(
        delete(EventParticipantTable).where(
            EventParticipantTable.entity_id == source_id,
            EventParticipantTable.event_id.in_(
                select(EventParticipantTable.event_id).where(EventParticipantTable.entity_id == target_id)
            ),
        )
    )
    event_participants = (
        await session.execute(
            update(EventParticipantTable)
            .where(EventParticipantTable.entity_id == source_id)
            .values(entity_id=target_id)
        )
    ).rowcount or 0

    comments = (
        await session.execute(
            update(CommentTable)
            .where(
                CommentTable.commentable_id == source_id,
                CommentTable.commentable_type.in_([CommentableType.PERSON, CommentableType.ENTITY]),
            )
            .values(commentable_id=target_id)
        )
    ).rowcount or 0

    return {
        "mentions": mentions,
        "relationships": relationships,
        "relationship_candidates": relationship_candidates,
        "entity_matches": entity_matches,
        "event_participants": event_participants,
        "comments": comments,
    }


def _collides(existing, *, column: str, target_id: str, key_cols: tuple[str, ...], extra: tuple = ()):
    """`EXISTS` a row on ``target_id`` sharing ``key_cols`` with the outer entity_match row."""
    return (
        select(literal(1))
        .select_from(existing)
        .where(
            existing.c[column] == target_id,
            *[existing.c[k] == getattr(EntityMatchTable, k) for k in key_cols],
            *extra,
        )
        .exists()
    )


async def _repoint_entity_matches(session: AsyncSession, *, source_id: str, target_id: str) -> int:
    """Repoint `entity_match` rows, dropping ones that would break its three unique keys.

    Keys: ``(mention_id, entity_id)``; the name-group ``(dataset_id, normalized_value,
    entity_id)``; the merge ``(dataset_id, provisional_entity_id, entity_id)``. On a
    name-group collision a decided source row wins over a pending target row, so a
    confirmed group stays confirmed on the survivor. A merge proposal left pointing
    the survivor at itself is dropped (pending) or un-flagged (decided, kept as audit).
    """
    t = EntityMatchTable
    existing = t.__table__.alias("existing")
    source_side = t.__table__.alias("source_side")
    is_group = and_(t.mention_id.is_(None), t.normalized_value.is_not(None))

    await session.execute(
        delete(t).where(
            t.entity_id == target_id,
            is_group,
            t.status == EntityMatchStatus.PENDING,
            _collides(
                source_side,
                column="entity_id",
                target_id=source_id,
                key_cols=("dataset_id", "normalized_value"),
                extra=(source_side.c.mention_id.is_(None), source_side.c.status != EntityMatchStatus.PENDING),
            ),
        )
    )
    for key_cols, scope in (
        (("mention_id",), t.mention_id.is_not(None)),
        (("dataset_id", "normalized_value"), is_group),
        (("dataset_id", "provisional_entity_id"), t.provisional_entity_id.is_not(None)),
    ):
        await session.execute(
            delete(t).where(
                t.entity_id == source_id,
                scope,
                _collides(existing, column="entity_id", target_id=target_id, key_cols=key_cols),
            )
        )
    moved = (await session.execute(update(t).where(t.entity_id == source_id).values(entity_id=target_id))).rowcount or 0

    await session.execute(
        delete(t).where(
            t.provisional_entity_id == source_id,
            _collides(
                existing, column="provisional_entity_id", target_id=target_id, key_cols=("dataset_id", "entity_id")
            ),
        )
    )
    await session.execute(update(t).where(t.provisional_entity_id == source_id).values(provisional_entity_id=target_id))
    self_merge = t.provisional_entity_id == t.entity_id
    await session.execute(delete(t).where(self_merge, t.status == EntityMatchStatus.PENDING))
    await session.execute(update(t).where(self_merge).values(provisional_entity_id=None))
    return moved


async def fold_entity(session: AsyncSession, *, source_id: str, target_id: str) -> dict[str, int]:
    """Fold entity ``source_id`` into ``target_id``: repoint, keep its names as aliases, delete it.

    The source's display name and aliases join the target's aliases (and its
    person's, for a person bridge -- `upsert_person_entity` mirrors those), and
    the target is re-keyed so the next resolution pass matches the old spelling
    straight to the survivor. Runs in the caller's transaction; does not commit.

    Raises:
        ValueError: if the ids are equal or either entity is missing.
    """
    if source_id == target_id:
        raise ValueError("cannot merge an entity into itself")
    rows = (await session.execute(select(EntityTable).where(EntityTable.id.in_([source_id, target_id])))).scalars()
    by_id = {r.id: r for r in rows}
    source, target = by_id.get(source_id), by_id.get(target_id)
    if source is None or target is None:
        raise ValueError(f"entity not found: {source_id if source is None else target_id}")
    source_names = [source.display_name, *(source.aliases or [])]

    moved = await repoint_entity_references(session, source_id=source_id, target_id=target_id)
    await session.execute(delete(EntityTable).where(EntityTable.id == source_id))

    aliases = _merged_aliases(target.display_name, [*(target.aliases or []), *source_names])
    await session.execute(update(EntityTable).where(EntityTable.id == target_id).values(aliases=aliases))
    if target.person_id:
        person = await session.get(PersonTable, target.person_id)
        if person is not None:
            person.aliases = _merged_aliases(person.name or target.display_name, [*person.aliases, *source_names])
    await refresh_entity_name_keys(
        session,
        entity_id=target_id,
        entity_type=target.entity_type,
        display_name=target.display_name,
        aliases=aliases,
    )
    return moved


def _merged_aliases(display_name: str, names: list[str]) -> list[str]:
    """Order-preserving, case-insensitive union of ``names`` minus the display name itself."""
    seen = {display_name.casefold()}
    out = []
    for name in names:
        if name and name.casefold() not in seen:
            seen.add(name.casefold())
            out.append(name)
    return out
