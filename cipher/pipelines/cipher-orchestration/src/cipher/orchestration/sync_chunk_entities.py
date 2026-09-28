"""Denormalize `mention` rows onto the Elasticsearch `text_chunks` index.

Runs *after* `extract-selectors` / `extract-entities` (mentions don't exist at
embed time). For every text-anchored mention it finds the chunk whose span
contains the mention's start offset and writes the aggregated entity metadata
(`entity_ids`, `entity_types`, `selector_types`, `selector_subtypes`,
`mention_count`) onto that chunk doc. This is what lets an entity filter compose
with a BM25 / kNN query and be faceted -- see `docs` / the search API.

Idempotent: each run overwrites those five fields on every chunk that has
mentions. Pass `purge=True` to also clear chunks that no longer have any
(after `reset-entities`).
"""

import bisect
from typing import TYPE_CHECKING

from loguru import logger
from tqdm import tqdm

from cipher.datastores.postgres.repositories import PostgresMentionRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _chunk_for_offset(starts: list[int], ends: list[int], offset: int) -> int | None:
    """Index of the chunk whose ``[start, end)`` contains ``offset`` (chunks are sorted, non-overlapping)."""
    i = bisect.bisect_right(starts, offset) - 1
    if 0 <= i < len(starts) and starts[i] <= offset < ends[i]:
        return i
    return None


async def sync_chunk_entities_workflow(
    session: "AsyncSession",
    es_client,
    dataset_id: str,
    *,
    purge: bool = False,
) -> dict[str, int]:
    """Sync a dataset's mentions onto its chunk docs. Returns a summary dict."""
    from cipher.datastores.elasticsearch.repositories.text_chunk import ElasticsearchTextChunkRepository

    es_repo = ElasticsearchTextChunkRepository(client=es_client)
    mention_repo = PostgresMentionRepository(session=session)

    # Add the denormalization fields to the existing index if it predates them
    # (new keyword/integer fields don't need a reindex).
    await es_client.indices.put_mapping(
        index=es_repo.index,
        body={
            "properties": {
                "entity_ids": {"type": "keyword"},
                "entity_types": {"type": "keyword"},
                "selector_types": {"type": "keyword"},
                "selector_subtypes": {"type": "keyword"},
                "mention_count": {"type": "integer"},
            }
        },
    )

    if purge:
        await es_client.update_by_query(
            index=es_repo.index,
            conflicts="proceed",
            body={
                "query": {"term": {"dataset_id": dataset_id}},
                "script": {
                    "source": (
                        "ctx._source.entity_ids=[]; ctx._source.entity_types=[]; "
                        "ctx._source.selector_types=[]; ctx._source.selector_subtypes=[]; "
                        "ctx._source.mention_count=0;"
                    )
                },
            },
        )

    rows = await mention_repo.entity_rows_for_chunk_sync(dataset_id=dataset_id)
    by_file: dict[str, list[dict]] = {}
    for row in rows:
        by_file.setdefault(row["file_id"], []).append(row)

    updates: dict[str, dict] = {}
    unplaced = 0
    for file_id, file_rows in tqdm(by_file.items(), desc="Syncing chunk entities", unit=" file"):
        chunks = await es_repo.list_by_file_id(file_id)
        if not chunks:
            continue
        chunks.sort(key=lambda c: c.start_offset)
        starts = [c.start_offset for c in chunks]
        ends = [c.end_offset for c in chunks]

        buckets: dict[int, list[dict]] = {}
        for row in file_rows:
            idx = _chunk_for_offset(starts, ends, row["start_offset"])
            if idx is None:
                unplaced += 1
                continue
            buckets.setdefault(idx, []).append(row)

        for idx, bucket in buckets.items():
            updates[chunks[idx].id] = {
                "entity_ids": sorted({r["entity_id"] for r in bucket if r["entity_id"]}),
                "entity_types": sorted({r["entity_type"] for r in bucket if r["entity_type"]}),
                "selector_types": sorted({r["selector_type"] for r in bucket if r["selector_type"]}),
                "selector_subtypes": sorted({r["selector_subtype"] for r in bucket if r["selector_subtype"]}),
                "mention_count": len(bucket),
            }

    updated = failed = 0
    if updates:
        updated, failed = await es_repo.attach_chunk_entities(updates)

    summary = {
        "mentions": len(rows),
        "files": len(by_file),
        "chunks_updated": updated,
        "chunks_failed": failed,
        "unplaced_mentions": unplaced,
    }
    logger.success(f"sync-chunk-entities: {summary}")
    return summary
