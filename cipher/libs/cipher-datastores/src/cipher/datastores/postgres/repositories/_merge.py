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

from cipher.datastores.postgres.tables.comment import CommentTable
from cipher.datastores.postgres.tables.entity_match import EntityMatchTable
from cipher.datastores.postgres.tables.entity_relationship import EntityRelationshipTable
from cipher.datastores.postgres.tables.entity_relationship_candidate import EntityRelationshipCandidateTable
from cipher.datastores.postgres.tables.event_participant import EventParticipantTable
from cipher.datastores.postgres.tables.mention import MentionTable
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

    # entity_match: mention -> entity resolution decisions, unique on
    # (mention_id, entity_id). Repoint the canonical side (dropping rows a target
    # row would collide with) and the provisional side, then null a provisional
    # pointer that now equals its own canonical entity.
    await session.execute(
        delete(EntityMatchTable).where(
            EntityMatchTable.entity_id == source_id,
            EntityMatchTable.mention_id.in_(
                select(EntityMatchTable.mention_id).where(EntityMatchTable.entity_id == target_id)
            ),
        )
    )
    entity_matches = (
        await session.execute(
            update(EntityMatchTable).where(EntityMatchTable.entity_id == source_id).values(entity_id=target_id)
        )
    ).rowcount or 0
    await session.execute(
        update(EntityMatchTable)
        .where(EntityMatchTable.provisional_entity_id == source_id)
        .values(provisional_entity_id=target_id)
    )
    await session.execute(
        update(EntityMatchTable)
        .where(EntityMatchTable.provisional_entity_id == EntityMatchTable.entity_id)
        .values(provisional_entity_id=None)
    )

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
