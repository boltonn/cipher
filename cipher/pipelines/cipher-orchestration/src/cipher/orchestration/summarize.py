"""File summaries (`text_summarization`): an LLM's 2-4 sentence description of one file, made on request.

Opt-in -- an LLM call per file is too slow to run on every file of a 10k-file dataset by
default. Two ways in: the file viewer's Summarize button (`summarize_file`, one file) and
`cipher summarize` (`summarize_workflow`, enrichment-gated, concurrent). Either way the result
is kept as a summary chunk, and content-identical files (any dataset) reuse it instead of calling the model.

Storage: a summary is a chunk (`is_summary`, chunk_index -1) per dataset + content hash,
so it is searchable like any chunk once embedded, and every identical file shares it.

What gets summarized: a file's extracted text (documents, emails, OCR'd images), or for a
table its stored sample rows plus the column mapping -- tables need no text extraction.
"""

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy import select
from tqdm import tqdm

from cipher.datastores.postgres.repositories import (
    PostgresEnrichmentRepository,
    PostgresExtractedTextRepository,
    PostgresTableMappingRepository,
)
from cipher.datastores.postgres.repositories.chunk_retrieval import PostgresChunkRetrievalRepository
from cipher.datastores.postgres.tables.file import FileTable
from cipher.schemas.content.search import TextChunk
from cipher.schemas.ingestion.enrichment import (
    DEFAULT_FILETYPE_GROUPS,
    TEXT_NATIVE_GROUPS,
    EnrichableType,
    EnrichmentType,
)
from cipher.schemas.ingestion.table_mapping import OTHER_FIELD, TableMappingRecord

if TYPE_CHECKING:
    from pyprompt import PromptRunner
    from sqlalchemy.ext.asyncio import AsyncSession

MIN_TEXT_CHARS = 40
TABLE_PREVIEW_ROWS = 25
TABLE_CELL_CHARS = 60
TABLE_GROUP = "table"


@dataclass(frozen=True, slots=True)
class SummaryInput:
    title: str
    filetype: str
    content: str


def _table_content(record: TableMappingRecord) -> str:
    """A table as the model reads it: what the columns hold, how rows connect, and sample rows."""
    mapping, sample = record.mapping, record.sample
    lines = [f"About {mapping.rows_estimate or len(sample.rows):,} rows."]
    typed = [f"{c.header} = {c.field_type}" for c in mapping.columns if c.field_type != OTHER_FIELD]
    if typed:
        lines.append("Columns: " + "; ".join(typed))
    for edge in mapping.edges:
        if edge.is_enabled:
            lines.append(f"Each row: {edge.src_slot} -{edge.relationship_type}-> {edge.dst_slot}")
    lines.append("| " + " | ".join(sample.headers) + " |")
    for row in sample.rows[:TABLE_PREVIEW_ROWS]:
        cells = [cell[:TABLE_CELL_CHARS].replace("|", "/").replace("\n", " ") for cell in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


async def summary_input(session: "AsyncSession", file: FileTable) -> SummaryInput | None:
    """What to summarize for a file, or None when it has nothing readable yet."""
    filetype = f"{file.filetype_group}, {file.filetype}"
    if file.table_sheets:
        mappings = PostgresTableMappingRepository(session=session)
        parts = []
        for sheet in file.table_sheets:
            record = await mappings.get_by_fingerprint(dataset_id=file.dataset_id, fingerprint=sheet["fingerprint"])
            if record is not None:
                label = f"Sheet {sheet['sheet']}\n" if sheet.get("sheet") else ""
                parts.append(label + _table_content(record))
        if parts:
            return SummaryInput(title=file.filename, filetype=filetype, content="\n\n".join(parts))
    extracted = await PostgresExtractedTextRepository(session=session).get_by_file_id(file.id)
    if extracted is None or sum(ch.isalnum() for ch in extracted.content) < MIN_TEXT_CHARS:
        return None
    return SummaryInput(title=file.filename, filetype=filetype, content=extracted.content)


Embed = Callable[[str], Awaitable[list[float]]]
"""Passage embedding for a summary chunk (the chunk store's model). None: `embed-text` fills it in later."""


async def existing_summary(session: "AsyncSession", file: FileTable) -> TextChunk | None:
    """The dataset's summary chunk for this file's content, if any."""
    return await PostgresChunkRetrievalRepository(session=session).summary_for(
        dataset_id=file.dataset_id, sha256=file.sha256
    )


async def _store(
    session: "AsyncSession", file: FileTable, *, text: str, model: str | None, embedding: list[float] | None
) -> None:
    """Write the summary chunk shared by every file in the dataset with this content."""
    duplicates = (
        await session.execute(
            select(FileTable.id).where(FileTable.dataset_id == file.dataset_id, FileTable.sha256 == file.sha256)
        )
    ).scalars()
    await PostgresChunkRetrievalRepository(session=session).upsert_summary(
        dataset_id=file.dataset_id,
        file_id=file.id,
        sha256=file.sha256,
        filetype_group=file.filetype_group,
        duplicate_file_ids=sorted({file.id, *duplicates}),
        text=text.strip(),
        generated_by=model,
        embedding=embedding,
    )


async def _reuse(session: "AsyncSession", file: FileTable) -> bool:
    """Copy this content's summary from another dataset (with its embedding) instead of calling the model."""
    found = await PostgresChunkRetrievalRepository(session=session).any_summary(file.sha256)
    if found is None:
        return False
    text, model, embedding = found
    await _store(session, file, text=text, model=model, embedding=embedding or None)
    return True


async def summarize_file(
    session: "AsyncSession",
    runner: "PromptRunner",
    file_id: str,
    *,
    embed: Embed | None = None,
    force: bool = False,
    language: str = "English",
    model: str | None = None,
) -> TextChunk | None:
    """Summarize one file now (the Summarize button) and return its summary chunk; None when there's nothing to read.

    Cached: the dataset's summary for this content is returned unless `force`; another dataset's is reused.
    """
    file = await session.get(FileTable, file_id)
    if file is None:
        return None
    if not force:
        if (cached := await existing_summary(session, file)) is not None:
            return cached
        if await _reuse(session, file):
            await session.commit()
            return await existing_summary(session, file)
    source = await summary_input(session, file)
    if source is None:
        return None
    result = await runner.summarize(
        source.content, title=source.title, filetype=source.filetype, language=language, model=model
    )
    embedding = await embed(result.summary) if embed else None
    await _store(session, file, text=result.summary, model=model or runner.model_name, embedding=embedding)
    await session.commit()
    return await existing_summary(session, file)


async def _queue(session: "AsyncSession", dataset_id: str, filetype_groups: Sequence[str]) -> int:
    """Documents, emails and tables by group (tables read their mapping); other groups only when they have text."""
    enrichments = PostgresEnrichmentRepository(session=session)
    count = 0
    for group in filetype_groups:
        queue = (
            enrichments.queue_enrichments_by_filter
            if group in TEXT_NATIVE_GROUPS or group == TABLE_GROUP
            else enrichments.queue_files_with_text
        )
        count += await queue(
            dataset_id=dataset_id, enrichment_type=EnrichmentType.TEXT_SUMMARIZATION, filetype_group=group
        )
    await session.commit()
    return count


async def summarize_workflow(
    session: "AsyncSession",
    dataset_id: str,
    *,
    filetype_groups: Sequence[str] = DEFAULT_FILETYPE_GROUPS[EnrichmentType.TEXT_SUMMARIZATION],
    concurrency: int = 8,
    batch_size: int = 50,
    limit: int | None = None,
    language: str = "English",
    model: str | None = None,
) -> dict[str, int]:
    """Summarize a dataset's files (opt-in enrichment). Files already summarized (or with a summarized twin) cost nothing."""
    from pyprompt import PromptRunner, Settings

    runner = PromptRunner(Settings())
    enrichments = PostgresEnrichmentRepository(session=session)
    await _queue(session, dataset_id, filetype_groups)
    pending = dict(
        enrichment_type=EnrichmentType.TEXT_SUMMARIZATION, enrichable_type=EnrichableType.FILE, dataset_id=dataset_id
    )
    total = await enrichments.count_pending(**pending)
    counts = {"files": 0, "llm_calls": 0, "reused": 0, "cached": 0, "skipped": 0, "failed": 0}
    semaphore = asyncio.Semaphore(concurrency)

    async def call(source: SummaryInput):
        async with semaphore:
            try:
                return await runner.summarize(
                    source.content, title=source.title, filetype=source.filetype, language=language, model=model
                )
            except Exception as exc:  # noqa: BLE001 -- one failed call fails one file, not the run
                return exc

    with tqdm(total=min(total, limit or total), desc="Summarizing", unit=" file") as progress:
        while limit is None or counts["files"] < limit:
            size = batch_size if limit is None else min(batch_size, limit - counts["files"])
            batch = await enrichments.get_pending_batch(batch_size=size, **pending)
            if not batch:
                break
            await enrichments.mark_processing(enrichment_ids=[item.enrichment.id for item in batch])
            await session.commit()

            # The session isn't safe across concurrent tasks: read everything, call the model in parallel, then write.
            completed, skipped, failed, todo = [], {}, {}, []
            files: dict[str, FileTable] = {}
            for item in batch:
                file = await session.get(FileTable, item.resource["id"])
                if file is not None:
                    files[item.enrichment.id] = file
                if file is None:
                    skipped[item.enrichment.id] = "file gone"
                elif await existing_summary(session, file) is not None:
                    counts["cached"] += 1
                    completed.append(item.enrichment.id)
                elif await _reuse(session, file):
                    counts["reused"] += 1
                    completed.append(item.enrichment.id)
                elif (source := await summary_input(session, file)) is None:
                    skipped[item.enrichment.id] = "no text to summarize"
                else:
                    todo.append((item, source))

            results = await asyncio.gather(*(call(source) for _, source in todo))
            for (item, _), result in zip(todo, results, strict=True):
                if isinstance(result, Exception):
                    logger.warning(f"Summary failed for {item.resource['filename']}: {result}")
                    failed[item.enrichment.id] = result
                    continue
                await _store(
                    session,
                    files[item.enrichment.id],
                    text=result.summary,
                    model=model or runner.model_name,
                    embedding=None,  # `cipher embed-text` embeds summary chunks (no model loaded here)
                )
                completed.append(item.enrichment.id)
                counts["llm_calls"] += 1

            if completed:
                await enrichments.mark_completed_batch(completed)
            if skipped:
                await enrichments.mark_skipped(skipped)
            await enrichments.mark_failed(failed)
            await session.commit()
            counts["files"] += len(batch)
            counts["skipped"] += len(skipped)
            counts["failed"] += len(failed)
            progress.update(len(batch))

    await runner.aclose()
    logger.success(f"Summaries for dataset {dataset_id}: {counts}")
    return counts
