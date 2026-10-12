"""Redo, for single files, steps that already read their text (an admin's choice after a correction).

`affected_by_text_change()` (from `ENRICHMENT_DEPENDENCIES`) says which steps a text
change reaches. The ones that can be redone for single files have a handler here: it
clears that step's machine-made output for those files (analyst work stays) and sets the
step back to pending, so its next run reads the new text. Text embedding has no handler:
`correct_text` rebuilds the chunks itself. After a correction, selector and entity
extraction only add mentions where the text changed (`correction_filter`).
"""

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from sqlalchemy import delete, select

from cipher.datastores.postgres.repositories import PostgresEnrichmentRepository
from cipher.datastores.postgres.repositories.tag import PostgresTagRepository
from cipher.datastores.postgres.tables.chunk import ChunkTable
from cipher.datastores.postgres.tables.enrichment import EnrichmentTable
from cipher.datastores.postgres.tables.event import EventTable
from cipher.schemas._base.base import BaseModel
from cipher.schemas.graph.event import EVENT_FILE_TAG
from cipher.schemas.ingestion.enrichment import (
    EnrichableType,
    EnrichmentType,
    ProcessingStatus,
    affected_by_text_change,
)
from cipher.schemas.interaction.tag import TagTargetType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

Restager = Callable[["AsyncSession", list[str], list[str]], Awaitable[None]]


async def _requeue_only(session: "AsyncSession", file_ids: list[str], sha256s: list[str]) -> None:
    """Nothing to clear: what the old text produced was already carried across or deleted with it."""


async def _clear_events(session: "AsyncSession", file_ids: list[str], sha256s: list[str]) -> None:
    """Drop the LLM's unverified events from these files and the event gate's verdict on their content."""
    await session.execute(
        delete(EventTable).where(
            EventTable.file_id.in_(file_ids), EventTable.extractor == "llm", ~EventTable.is_verified
        )
    )
    await PostgresTagRepository(session).forget_model(
        target_type=TagTargetType.CONTENT, target_ids=sha256s, tag=EVENT_FILE_TAG
    )


async def _clear_summaries(session: "AsyncSession", file_ids: list[str], sha256s: list[str]) -> None:
    """Drop the content's summaries in every dataset; the file page writes a fresh one on request."""
    await session.execute(delete(ChunkTable).where(ChunkTable.sha256.in_(sha256s), ChunkTable.is_summary))


RESTAGERS: dict[EnrichmentType, Restager] = {
    EnrichmentType.SELECTOR_EXTRACTION: _requeue_only,
    EnrichmentType.ENTITY_EXTRACTION: _requeue_only,
    EnrichmentType.EVENT_EXTRACTION: _clear_events,
    EnrichmentType.TEXT_SUMMARIZATION: _clear_summaries,
}
REBUILT_IN_PLACE = frozenset({EnrichmentType.TEXT_EMBEDDING})


class TextChangeImpact(BaseModel):
    """The steps that already read these files' text: the ones that can be redone, and any running now."""

    rerunnable: list[EnrichmentType] = []
    running: list[EnrichmentType] = []


async def text_change_impact(session: "AsyncSession", *, file_ids: list[str]) -> TextChangeImpact:
    """Look up the affected steps' state on these files (pending ones will read the new text anyway)."""
    rows = await session.execute(
        select(EnrichmentTable.enrichment_type, EnrichmentTable.status)
        .where(
            EnrichmentTable.enrichable_type == EnrichableType.FILE,
            EnrichmentTable.enrichable_id.in_(file_ids),
            EnrichmentTable.enrichment_type.in_(affected_by_text_change()),
            EnrichmentTable.status != ProcessingStatus.PENDING,
        )
        .distinct()
    )
    rerunnable, running = set(), set()
    for enrichment_type, status in rows.tuples():
        if status == ProcessingStatus.PROCESSING:
            running.add(enrichment_type)
        elif enrichment_type in RESTAGERS or enrichment_type in REBUILT_IN_PLACE:
            rerunnable.add(enrichment_type)
    return TextChangeImpact(rerunnable=sorted(rerunnable), running=sorted(running))


async def restage_text_readers(
    session: "AsyncSession", *, file_ids: list[str], sha256s: list[str], steps: list[EnrichmentType]
) -> None:
    """Clear and re-queue these steps for these files. Caller commits."""
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    for enrichment_type in steps:
        await RESTAGERS[enrichment_type](session, file_ids, sha256s)
        await enrichment_repo.requeue(file_ids=file_ids, enrichment_type=enrichment_type)
