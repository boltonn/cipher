"""Recompute normalization / validation / attributes for stored selector rows.

Retroactive backfill: run `pyselectors` over each `selector` row's `raw_value`
using the *current* packs and validators, and refresh `attributes` +
`region_hint` in place. `normalized_value` (the resolution blocking key) is left
alone -- a value that now normalizes differently is a merge, not a refresh.

Rows whose `raw_value` no longer validates are logged and skipped, not deleted.
"""

from typing import TYPE_CHECKING

from loguru import logger
from tqdm import tqdm

from cipher.datastores.postgres.repositories import PostgresEntityRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def refresh_selectors_workflow(
    session: "AsyncSession",
    dataset_id: str | None = None,
    *,
    commit_every: int = 200,
) -> dict[str, int]:
    """Refresh attributes/region_hint on every selector row. Returns a small summary dict."""
    from pyselectors import resolve_selector

    entity_repo = PostgresEntityRepository(session=session)
    selectors = await entity_repo.list_selectors(dataset_id=dataset_id)

    updated = unchanged = rejected = 0
    with tqdm(total=len(selectors), desc="Refreshing selectors", unit=" selector") as pbar:
        for index, selector in enumerate(selectors, start=1):
            spans = resolve_selector(
                selector.raw_value,
                selector_type=selector.selector_type,
                selector_subtype=selector.selector_subtype,
                region=selector.region_hint,
            )
            if not spans:
                rejected += 1
                logger.warning(
                    f"selector {selector.entity_id} ({selector.selector_type}) no longer validates: "
                    f"{selector.raw_value!r}"
                )
            else:
                span = spans[0]
                new_attrs = dict(span.attributes)
                new_region = span.region_hint
                if new_attrs != dict(selector.attributes) or new_region != selector.region_hint:
                    await entity_repo.refresh_selector(selector.entity_id, attributes=new_attrs, region_hint=new_region)
                    updated += 1
                else:
                    unchanged += 1

            if index % commit_every == 0:
                await session.commit()
            pbar.update(1)

    await session.commit()
    summary = {"total": len(selectors), "updated": updated, "unchanged": unchanged, "rejected": rejected}
    logger.success(f"Selector refresh: {summary}")
    return summary
