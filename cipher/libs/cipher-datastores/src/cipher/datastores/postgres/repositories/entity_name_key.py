"""Materialized name-blocking index for entity resolution (`entity_name_key`).

Two entry points:

* `refresh_entity_name_keys(...)` -- recompute one entity's key rows inside the
  caller's transaction. Wired into every `entity` write path.
* `PostgresEntityNameKeyRepository` -- `refresh_batch` for the backfill sweep,
  `candidates` for the resolution blocker, plus stats/reset helpers.

Only person / organization / location entities are keyed; selectors resolve by
exact value, not by name.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from sqlalchemy import delete, distinct, func, or_, select, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.tables.entity import EntityTable
from cipher.datastores.postgres.tables.entity_name_key import EntityNameKeyTable
from cipher.names import entity_keys
from cipher.schemas.graph.ontology import EntityType

_KEYED_TYPES: frozenset[EntityType] = frozenset({EntityType.PERSON, EntityType.ORGANIZATION, EntityType.LOCATION})
# asyncpg caps a statement at 32767 bind params; 3 columns per row -> stay well under.
_INSERT_CHUNK = 5000
_SELECT_CHUNK = 2000


def _pairs_for(entity_type: EntityType, display_name: str, aliases: Iterable[str]) -> set[tuple[str, str]]:
    if entity_type not in _KEYED_TYPES:
        return set()
    return entity_keys(display_name or "", aliases or [])


async def _replace_keys(session: AsyncSession, entity_id: str, pairs: set[tuple[str, str]]) -> int:
    await session.execute(delete(EntityNameKeyTable).where(EntityNameKeyTable.entity_id == entity_id))
    if not pairs:
        return 0
    await session.execute(
        pg_insert(EntityNameKeyTable)
        .values([{"entity_id": entity_id, "key_type": kt, "key": k} for kt, k in pairs])
        .on_conflict_do_nothing()
    )
    return len(pairs)


async def refresh_entity_name_keys(
    session: AsyncSession,
    *,
    entity_id: str,
    entity_type: EntityType,
    display_name: str,
    aliases: Iterable[str] = (),
) -> int:
    """Recompute one entity's `entity_name_key` rows. Does not commit -- runs in the caller's txn."""
    return await _replace_keys(session, entity_id, _pairs_for(entity_type, display_name, aliases))


@dataclass(frozen=True, slots=True)
class EntityKeyInput:
    """One entity to (re)key, as read from the `entity` table by the backfill sweep."""

    entity_id: str
    entity_type: EntityType
    display_name: str
    aliases: tuple[str, ...] = ()


class PostgresEntityNameKeyRepository:
    """Batch maintenance and candidate lookup over `entity_name_key`."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def refresh_batch(self, items: Sequence[EntityKeyInput]) -> dict[str, int]:
        """Recompute keys for a batch of entities. Commits per insert chunk."""
        entity_ids = [it.entity_id for it in items]
        keyed = 0
        rows: list[dict[str, str]] = []
        for start in range(0, len(entity_ids), _SELECT_CHUNK):
            chunk = entity_ids[start : start + _SELECT_CHUNK]
            await self.session.execute(delete(EntityNameKeyTable).where(EntityNameKeyTable.entity_id.in_(chunk)))
        for it in items:
            pairs = _pairs_for(it.entity_type, it.display_name, it.aliases)
            if pairs:
                keyed += 1
            rows.extend({"entity_id": it.entity_id, "key_type": kt, "key": k} for kt, k in pairs)

        written = 0
        for start in range(0, len(rows), _INSERT_CHUNK):
            batch = rows[start : start + _INSERT_CHUNK]
            await self.session.execute(pg_insert(EntityNameKeyTable).values(batch).on_conflict_do_nothing())
            written += len(batch)
            await self.session.commit()
        if not rows:
            await self.session.commit()
        return {"entities_keyed": keyed, "keys_written": written}

    async def candidates(
        self,
        *,
        keys: set[tuple[str, str]],
        dataset_id: str | None,
        entity_type: EntityType | None = None,
        cross_dataset: bool = False,
        exclude_entity_id: str | None = None,
        per_key_cap: int = 200,
        limit: int = 50,
    ) -> list[tuple[str, list[str]]]:
        """Entities sharing a blocking key with `keys`, best (most keys matched) first.

        Any single `(key_type, key)` matching more than `per_key_cap` entities is
        dropped as non-discriminative -- so a name whose surname is `li` still
        blocks on its precise keys without dragging in thousands of rows.
        Returns `(entity_id, [matched_key_types])`.
        """
        if not keys:
            return []
        pairs = list(keys)
        ek = EntityNameKeyTable
        key_pair = tuple_(ek.key_type, ek.key)

        hot = (
            select(ek.key_type, ek.key)
            .where(key_pair.in_(pairs))
            .group_by(ek.key_type, ek.key)
            .having(func.count() > per_key_cap)
        )

        where = [key_pair.in_(pairs), key_pair.not_in(hot)]
        if not cross_dataset:
            where.append(or_(EntityTable.dataset_id == dataset_id, EntityTable.dataset_id.is_(None)))
        if entity_type is not None:
            where.append(EntityTable.entity_type == entity_type)
        if exclude_entity_id is not None:
            where.append(ek.entity_id != exclude_entity_id)

        stmt = (
            select(ek.entity_id, func.array_agg(distinct(ek.key_type)))
            .join(EntityTable, EntityTable.id == ek.entity_id)
            .where(*where)
            .group_by(ek.entity_id)
            .order_by(func.count(distinct(ek.key_type)).desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [(row[0], list(row[1])) for row in result.all()]

    async def count(self) -> int:
        """Total key rows -- for the backfill CLI summary."""
        return (await self.session.execute(select(func.count()).select_from(EntityNameKeyTable))).scalar_one()

    async def delete_all(self) -> int:
        """Drop every key row (used by `backfill-entity-name-keys --reset`)."""
        result = await self.session.execute(delete(EntityNameKeyTable))
        await self.session.commit()
        return result.rowcount or 0
