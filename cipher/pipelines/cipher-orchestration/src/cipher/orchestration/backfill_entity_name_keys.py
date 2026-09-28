"""Populate / rebuild the `entity_name_key` blocking index.

A dataset-wide (or global) sweep that recomputes `cipher.names.entity_keys` for
every person / organization / location entity and replaces its rows in
`entity_name_key`. Idempotent: each entity's rows are delete-then-insert, so a
re-run heals drift and a `cipher-names` `KEYS_VERSION` bump just needs another
pass.

Thereafter the index stays current on its own -- every `entity` write refreshes
its keys inline, and `ON DELETE CASCADE` drops them with the entity. This sweep
is for initial adoption and post-upgrade rebuilds.

Scale: ~8 keys/entity, chunked inserts. 100k entities -> ~0.8M rows in a few
seconds; 1M entities -> ~8M rows in ~a minute.
"""

from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy import select
from tqdm import tqdm

from cipher.datastores.postgres.repositories.entity_name_key import (
    EntityKeyInput,
    PostgresEntityNameKeyRepository,
)
from cipher.datastores.postgres.tables.entity import EntityTable
from cipher.schemas.graph.ontology import EntityType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_KEYED_TYPES = (EntityType.PERSON, EntityType.ORGANIZATION, EntityType.LOCATION)


async def backfill_entity_name_keys_workflow(
    session: "AsyncSession",
    *,
    dataset_id: str | None = None,
    batch_size: int = 1000,
    purge: bool = False,
) -> dict[str, int]:
    """Recompute `entity_name_key` for keyed entities. Returns per-outcome counts."""
    repo = PostgresEntityNameKeyRepository(session=session)

    if purge and dataset_id is None:
        removed = await repo.delete_all()
        logger.info(f"Purged {removed} existing key rows")

    scanned = keyed = written = 0
    last_id = ""
    with tqdm(desc="Keying entities", unit=" entity") as bar:
        while True:
            query = (
                select(EntityTable.id, EntityTable.entity_type, EntityTable.display_name, EntityTable.aliases)
                .where(EntityTable.entity_type.in_(_KEYED_TYPES), EntityTable.id > last_id)
                .order_by(EntityTable.id)
                .limit(batch_size)
            )
            if dataset_id is not None:
                query = query.where(EntityTable.dataset_id == dataset_id)
            rows = (await session.execute(query)).all()
            if not rows:
                break

            items = [
                EntityKeyInput(
                    entity_id=r.id,
                    entity_type=r.entity_type,
                    display_name=r.display_name or "",
                    aliases=tuple(r.aliases or ()),
                )
                for r in rows
            ]
            result = await repo.refresh_batch(items)
            scanned += len(items)
            keyed += result["entities_keyed"]
            written += result["keys_written"]
            last_id = rows[-1].id
            bar.update(len(items))

    counts = {"entities_scanned": scanned, "entities_keyed": keyed, "keys_written": written}
    logger.success(f"Backfilled entity_name_key ({dataset_id or 'all datasets'}): {counts}")
    return counts
