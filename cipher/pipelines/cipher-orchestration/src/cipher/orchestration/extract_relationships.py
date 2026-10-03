"""Relationship extraction workflow (RELATIONSHIP_EXTRACTION enrichment).

Scope for now: **directed email `emailed` edges between address selectors.**
For every email, an `emailed` edge runs from the `from` address to each `to` /
`cc` / `bcc` address, endpoint = the `email` selector entity `extract-selectors`
already created. No name resolution is needed -- the ontology allows bare
`selector -> selector` comms endpoints, so this runs off header selectors alone.

A reply is its own edge the other way. Edges are deduped on the `(src, dst,
relationship_type)` unique constraint and carry `weight` = emails sent src -> dst,
plus the `date_observed_start` / `_end` span of those emails. `source =
selector_inference`.

Person/org `has_selector` edges (an address -> the human who uses it) are NOT
built here: they need a resolved person entity, which waits on
`resolve-entities`.

Re-runnable: enrichment-queue guarded, so a second run without `reset-entities`
processes nothing and never double-counts `weight`; `rebuild=True` drops this
workflow's edges and recomputes them.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from tqdm import tqdm

from cipher.datastores.postgres.repositories import (
    PostgresEnrichmentRepository,
    PostgresExtractedTextRepository,
)
from cipher.datastores.postgres.tables.entity_relationship import EntityRelationshipTable
from cipher.datastores.postgres.tables.selector import SelectorTable
from cipher.schemas.content.email import EmailMetadata
from cipher.schemas.graph.ontology import RelationshipSource, RelationshipType, SelectorType
from cipher.schemas.ingestion.enrichment import EnrichableType, EnrichmentType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_EMAIL_FILETYPE_GROUP = "email"
_UPSERT_CHUNK = 1000
# Relationship types this workflow owns.
_OWNED_TYPES = (RelationshipType.EMAILED,)


@dataclass
class _EdgeAgg:
    """Per-run accumulation for one sender -> recipient selector pair."""

    messages: int = 0
    dates: list[datetime] = field(default_factory=list)

    def observe(self, date_sent: datetime | None) -> None:
        self.messages += 1
        if date_sent is not None:
            self.dates.append(date_sent)


def _recipient_addresses(metadata: EmailMetadata) -> list[str]:
    return [p.value for p in (*metadata.sent_to, *metadata.cc, *metadata.bcc)]


async def _load_email_selector_index(session: "AsyncSession", dataset_id: str) -> dict[str, str]:
    """Normalized email address -> selector entity id, for the whole dataset."""
    rows = (
        await session.execute(
            select(SelectorTable.normalized_value, SelectorTable.entity_id).where(
                SelectorTable.dataset_id == dataset_id,
                SelectorTable.selector_type == SelectorType.EMAIL,
            )
        )
    ).all()
    return {normalized_value: entity_id for normalized_value, entity_id in rows}


async def _flush_edges(session: "AsyncSession", dataset_id: str, edges: dict[tuple[str, str], _EdgeAgg]) -> int:
    """Upsert a batch of accumulated edges, widening weight + observed-date span. Returns pairs written."""
    if not edges:
        return 0

    items = list(edges.items())
    for start in range(0, len(items), _UPSERT_CHUNK):
        chunk = items[start : start + _UPSERT_CHUNK]
        values = [
            {
                "dataset_id": dataset_id,
                "src_entity_id": src,
                "dst_entity_id": dst,
                "relationship_type": RelationshipType.EMAILED,
                "directed": True,
                "weight": float(agg.messages),
                "source": RelationshipSource.SELECTOR_INFERENCE,
                "attributes": {},
                "date_observed_start": min(agg.dates) if agg.dates else None,
                "date_observed_end": max(agg.dates) if agg.dates else None,
            }
            for (src, dst), agg in chunk
        ]
        insert_stmt = pg_insert(EntityRelationshipTable).values(values)
        await session.execute(
            insert_stmt.on_conflict_do_update(
                constraint="uq_entity_relationship_triple",
                set_={
                    "weight": func.coalesce(EntityRelationshipTable.weight, 0) + insert_stmt.excluded.weight,
                    "date_observed_start": func.least(
                        EntityRelationshipTable.date_observed_start, insert_stmt.excluded.date_observed_start
                    ),
                    "date_observed_end": func.greatest(
                        EntityRelationshipTable.date_observed_end, insert_stmt.excluded.date_observed_end
                    ),
                    "source": insert_stmt.excluded.source,
                },
            )
        )
    return len(edges)


def _email_edges(
    metadata: EmailMetadata, selector_index: dict[str, str]
) -> tuple[list[tuple[str, str]], datetime | None, int]:
    """(sender, recipient) selector-id pairs for one email. Returns (pairs, date_sent, unmapped)."""
    from pyselectors.normalize import normalize_email

    sender = metadata.sent_from or metadata.sender
    if sender is None:
        return [], metadata.date_sent, 0
    src = selector_index.get(normalize_email(sender.value))
    if src is None:
        return [], metadata.date_sent, 1

    pairs: list[tuple[str, str]] = []
    unmapped = 0
    seen: set[str] = set()
    for raw in _recipient_addresses(metadata):
        dst = selector_index.get(normalize_email(raw))
        if dst is None:
            unmapped += 1
            continue
        if dst == src or dst in seen:
            continue
        seen.add(dst)
        pairs.append((src, dst))
    return pairs, metadata.date_sent, unmapped


async def queue_relationship_extraction_enrichments(session: "AsyncSession", dataset_id: str) -> int:
    """Queue RELATIONSHIP_EXTRACTION enrichments for a dataset's email files."""
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    count = await enrichment_repo.queue_enrichments_by_filter(
        dataset_id=dataset_id,
        enrichment_type=EnrichmentType.RELATIONSHIP_EXTRACTION,
        filetype_group=_EMAIL_FILETYPE_GROUP,
    )
    await session.commit()
    return count


async def reset_selector_communication_edges(session: "AsyncSession", dataset_id: str) -> int:
    """Drop this workflow's edges and its enrichments so the next run recomputes them. Returns edges dropped."""
    result = await session.execute(
        delete(EntityRelationshipTable).where(
            EntityRelationshipTable.dataset_id == dataset_id,
            EntityRelationshipTable.relationship_type.in_(_OWNED_TYPES),
            EntityRelationshipTable.source == RelationshipSource.SELECTOR_INFERENCE,
        )
    )
    await PostgresEnrichmentRepository(session=session).delete_by_type(
        dataset_id, EnrichmentType.RELATIONSHIP_EXTRACTION
    )
    await session.commit()
    return result.rowcount or 0


async def extract_relationships_workflow(
    session: "AsyncSession",
    dataset_id: str,
    batch_size: int = 200,
    rebuild: bool = False,
) -> int:
    """Build directed email `emailed` edges between address selectors. Returns emails processed.

    Run `extract-selectors` first -- the edge endpoints are the `email`
    selector entities it creates; emails whose addresses have no selector
    entity are skipped.
    """
    if rebuild:
        dropped = await reset_selector_communication_edges(session=session, dataset_id=dataset_id)
        logger.info(f"Dropped {dropped} email edges to rebuild")
    await queue_relationship_extraction_enrichments(session=session, dataset_id=dataset_id)

    enrichment_repo = PostgresEnrichmentRepository(session=session)
    extracted_text_repo = PostgresExtractedTextRepository(session=session)
    selector_index = await _load_email_selector_index(session, dataset_id)
    if not selector_index:
        logger.warning("No email selector entities for this dataset -- run extract-selectors first. Nothing to do.")
        return 0

    total = await enrichment_repo.count_pending(
        enrichment_type=EnrichmentType.RELATIONSHIP_EXTRACTION,
        enrichable_type=EnrichableType.FILE,
        dataset_id=dataset_id,
        filetype_group_filter=_EMAIL_FILETYPE_GROUP,
    )
    count = failed_count = unmapped_count = 0
    seen_pairs: set[tuple[str, str]] = set()

    with tqdm(total=total, desc="Extracting relationships", unit=" email") as pbar:
        while True:
            batch = await enrichment_repo.get_pending_batch(
                enrichment_type=EnrichmentType.RELATIONSHIP_EXTRACTION,
                enrichable_type=EnrichableType.FILE,
                batch_size=batch_size,
                dataset_id=dataset_id,
                filetype_group_filter=_EMAIL_FILETYPE_GROUP,
            )
            if not batch:
                break

            await enrichment_repo.mark_processing(enrichment_ids=[item.enrichment.id for item in batch])
            await session.commit()

            batch_edges: dict[tuple[str, str], _EdgeAgg] = defaultdict(_EdgeAgg)
            completed, failed = [], {}
            for item in batch:
                try:
                    extracted = await extracted_text_repo.get_by_file_id(item.resource["id"])
                    if extracted is not None and isinstance(extracted.metadata, EmailMetadata):
                        pairs, date_sent, unmapped = _email_edges(extracted.metadata, selector_index)
                        unmapped_count += unmapped
                        for pair in pairs:
                            batch_edges[pair].observe(date_sent)
                    completed.append(item.enrichment.id)
                except Exception as e:
                    logger.error(f"Relationship extraction failed for file {item.resource['id']}: {e}")
                    failed[item.enrichment.id] = e

            try:
                await _flush_edges(session, dataset_id, batch_edges)
                seen_pairs.update(batch_edges)
                if completed:
                    await enrichment_repo.mark_completed_batch(completed)
                await enrichment_repo.mark_failed(failed)
                await session.commit()
            except Exception as e:
                logger.error(f"Edge flush failed for batch: {e}")
                await session.rollback()
                await enrichment_repo.mark_failed({**dict.fromkeys(completed, e), **failed})
                await session.commit()
                failed_count += len(completed) + len(failed)
                pbar.update(len(batch))
                continue

            count += len(completed)
            failed_count += len(failed)
            pbar.set_postfix(failed=failed_count, edges=len(seen_pairs))
            pbar.update(len(completed) + len(failed))

    logger.success(
        f"Built {len(seen_pairs)} emailed edges from {count} emails "
        f"({failed_count} failed, {unmapped_count} addresses with no selector entity)"
    )
    return count


async def get_relationship_extraction_stats(session: "AsyncSession", dataset_id: str | None = None) -> dict:
    """Enrichment stats for relationship extraction."""
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    return await enrichment_repo.get_enrichment_stats(
        enrichable_type=EnrichableType.FILE,
        dataset_id=dataset_id,
        enrichment_type=EnrichmentType.RELATIONSHIP_EXTRACTION,
    )
