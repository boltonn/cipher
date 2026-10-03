"""Combined LLM extraction pass -- entities/relations + events in one `pyprompt` call.

`extract-entities --extractor llm` and `extract-events --llm` each make their own
call over the same email/document text. `extract_llm_workflow` folds them into
one `runner.extract_all(...)` per file and completes both the `ENTITY_EXTRACTION`
and `EVENT_EXTRACTION` enrichments together. `--tasks` selects which sections the
model is asked for.

Scope: the email file set (plus `document` with `--docs`), same as
`extract-events --llm`. Entity extraction over *all* text, and the `nerd` /
`gliner` engines, stay with `extract-entities`.

**Cost guard.** LLM inference is the bottleneck: a bulk pass over tens of
thousands of files is an overnight job at best, and only with a fast served
model and real request concurrency. So this workflow (a) fires `--concurrency`
calls at once so the server can batch them, (b) logs a rolling
seconds/file + ETA so a developer watching sees a bad run early, and (c)
**refuses** to start a run larger than `max_files` (default
:data:`DEFAULT_MAX_LLM_PASS_FILES`) unless `yes=True` -- use `--limit` for a
bounded slice, or `--yes` to override once you have measured the rate.

Re-runnable via the same enrichment guard as the granular passes; `reset-entities`
/ `reset-events` clear what this writes.
"""

import asyncio
import time
from typing import TYPE_CHECKING

from loguru import logger
from tqdm import tqdm

from cipher.datastores.postgres.repositories import (
    PostgresEnrichmentRepository,
    PostgresEventRepository,
    PostgresExtractedTextRepository,
    PostgresMentionRelationshipRepository,
    PostgresMentionRepository,
)
from cipher.orchestration.extract_entities import persist_file_entities
from cipher.orchestration.extract_events import (
    _CALENDAR_MIME,
    TEXT_EVENT_GROUPS_EMAIL,
    _load_event_dedup_keys,
    _reference_date,
    persist_llm_events,
    tag_event_files,
)
from cipher.schemas.ingestion.enrichment import EnrichableType, EnrichmentType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_LLM_EXTRACTOR = "llm"
_KNOWN_TASKS = {"entities", "events"}

# A run bigger than this is refused without `yes=True`. Sized so a bounded pass
# finishes overnight with a fast served model + concurrency (~1-2 s/file); a
# slow model (or no concurrency) will not make it, which is the point.
DEFAULT_MAX_LLM_PASS_FILES = 15_000
# Once the measured pace projects past this, log a warning every batch.
_WARN_ETA_HOURS = 8.0
DEFAULT_CONCURRENCY = 8


class LlmPassTooLargeError(RuntimeError):
    """Raised when a combined LLM pass would exceed the per-run file cap."""


async def extract_llm_workflow(
    session: "AsyncSession",
    dataset_id: str,
    *,
    tasks: set[str],
    filetype_groups: tuple[str, ...] = TEXT_EVENT_GROUPS_EMAIL,
    batch_size: int = 20,
    concurrency: int = DEFAULT_CONCURRENCY,
    model: str | None = None,
    limit: int | None = None,
    max_files: int = DEFAULT_MAX_LLM_PASS_FILES,
    yes: bool = False,
) -> int:
    """One `pyprompt` call per file over the text set -> mentions + events. Returns files processed.

    `limit` caps files processed this run (for A/B slices); `concurrency` LLM
    calls are in flight at once; a run larger than `max_files` is refused unless
    `yes` is set. The rest stay pending for a later run.
    """
    tasks = {t.strip().lower() for t in tasks}
    unknown = tasks - _KNOWN_TASKS
    if unknown:
        raise ValueError(f"extract-llm: unknown task(s) {sorted(unknown)}; choose from {sorted(_KNOWN_TASKS)}")
    do_entities = "entities" in tasks
    do_events = "events" in tasks
    if not (do_entities or do_events):
        raise ValueError("extract-llm needs at least one task: entities, events")

    enrichment_repo = PostgresEnrichmentRepository(session=session)
    extracted_text_repo = PostgresExtractedTextRepository(session=session)
    mention_repo = PostgresMentionRepository(session=session)
    relation_repo = PostgresMentionRelationshipRepository(session=session)
    event_repo = PostgresEventRepository(session=session)

    for group in filetype_groups:
        if do_entities:
            await enrichment_repo.queue_enrichments_by_filter(
                dataset_id=dataset_id, enrichment_type=EnrichmentType.ENTITY_EXTRACTION, filetype_group=group
            )
        if do_events:
            await enrichment_repo.queue_enrichments_by_filter(
                dataset_id=dataset_id, enrichment_type=EnrichmentType.EVENT_EXTRACTION, filetype_group=group
            )
    await session.commit()

    primary_type = EnrichmentType.ENTITY_EXTRACTION if do_entities else EnrichmentType.EVENT_EXTRACTION
    secondary_type = EnrichmentType.EVENT_EXTRACTION if (do_entities and do_events) else None

    pending = 0
    for group in filetype_groups:
        pending += await enrichment_repo.count_pending(
            enrichment_type=primary_type,
            enrichable_type=EnrichableType.FILE,
            dataset_id=dataset_id,
            filetype_group_filter=group,
        )
    target = pending if limit is None else min(pending, limit)

    if target > max_files and not yes:
        raise LlmPassTooLargeError(
            f"{target:,} files would be processed this run, over the {max_files:,}-file cap for one LLM pass "
            f"(an overnight job even with a fast model + concurrency). The enrichments are queued; re-run with "
            f"`--limit N` (N <= {max_files:,}) for a bounded slice, or `--yes` to run the whole backlog."
        )

    from pyprompt import PromptRunner, Settings

    settings = Settings()
    runner = PromptRunner(settings)
    resolved_model = model or settings.llm.model
    logger.info(
        f"extract-llm: {target:,} files this run "
        f"(tasks={','.join(sorted(tasks))}, concurrency={concurrency}, model={resolved_model})"
    )

    seen = await _load_event_dedup_keys(session, dataset_id) if do_events else set()
    sem = asyncio.Semaphore(max(1, concurrency))
    started = time.monotonic()
    warned_eta = False

    count = failed_count = mention_count = relation_count = event_count = 0
    aborted = False
    attempted: set[str] = set()  # enrichment ids tried this run -- don't re-loop our own FAILEDs

    with tqdm(total=target, desc=f"Extracting (llm: {','.join(sorted(tasks))})", unit=" file") as pbar:
        for group in filetype_groups:
            if aborted:
                break
            while limit is None or count + failed_count < limit:
                remaining = batch_size if limit is None else min(batch_size, limit - count - failed_count)
                batch = await enrichment_repo.get_pending_batch(
                    enrichment_type=primary_type,
                    enrichable_type=EnrichableType.FILE,
                    batch_size=remaining,
                    dataset_id=dataset_id,
                    filetype_group_filter=group,
                )
                batch = [item for item in batch if item.enrichment.id not in attempted]
                if not batch:
                    break
                attempted.update(item.enrichment.id for item in batch)

                await enrichment_repo.mark_processing(enrichment_ids=[item.enrichment.id for item in batch])
                await session.commit()

                completed, failed, files_done = [], {}, []
                with_events, without_events = [], []

                # 1. resolve each file's text (serial DB reads); short-circuit empties.
                work = []
                for item in batch:
                    file_id = item.resource["id"]
                    if item.resource.get("mime_type") == _CALENDAR_MIME:
                        completed.append(item.enrichment.id)
                        files_done.append(file_id)
                        continue
                    extracted = await extracted_text_repo.get_by_file_id(file_id)
                    content = (extracted.content or "") if extracted is not None else ""
                    if not content.strip():
                        completed.append(item.enrichment.id)
                        files_done.append(file_id)
                        continue
                    work.append((item, extracted, content))

                # 2. fire the LLM calls concurrently so the server can batch them.
                async def _call(item, extracted, content):
                    async with sem:
                        try:
                            res = await runner.extract_all(
                                content, tasks=tasks, reference_date=_reference_date(extracted)
                            )
                            return item, extracted, content, res, None
                        except Exception as exc:  # noqa: BLE001 -- reported per file below
                            return item, extracted, content, None, exc

                results = await asyncio.gather(*(_call(*w) for w in work))

                # 3. persist serially (one shared session -> no concurrent writes).
                for item, extracted, content, res, err in results:
                    file_id = item.resource["id"]
                    if err is not None:
                        logger.error(f"Combined LLM extraction failed for file {file_id}: {err}")
                        failed[item.enrichment.id] = err
                        continue
                    try:
                        if do_entities:
                            written_mentions, written_relations = await persist_file_entities(
                                spans=list(res.entities.entities),
                                relations=list(res.entities.relations),
                                dataset_id=dataset_id,
                                file_id=file_id,
                                extracted_id=extracted.id,
                                content=content,
                                extractor=_LLM_EXTRACTOR,
                                model=resolved_model,
                                mention_repo=mention_repo,
                                relation_repo=relation_repo,
                            )
                            mention_count += written_mentions
                            relation_count += written_relations
                        if do_events:
                            event_count += await persist_llm_events(
                                res.events.events,
                                dataset_id=dataset_id,
                                file_id=file_id,
                                model=resolved_model,
                                seen=seen,
                                event_repo=event_repo,
                            )
                            (with_events if res.events.events else without_events).append(file_id)
                        completed.append(item.enrichment.id)
                        files_done.append(file_id)
                    except Exception as exc:  # noqa: BLE001
                        logger.error(f"Persisting combined LLM extraction failed for file {file_id}: {exc}")
                        await session.rollback()
                        failed[item.enrichment.id] = exc

                await tag_event_files(
                    session, with_events=with_events, without_events=without_events, model=resolved_model
                )
                if completed:
                    await enrichment_repo.mark_completed_batch(completed)
                await enrichment_repo.mark_failed(failed)
                if secondary_type and files_done:
                    secondary = await enrichment_repo.get_enrichment_ids_for(files_done, secondary_type)
                    if secondary:
                        await enrichment_repo.mark_completed_batch(list(secondary.values()))
                await session.commit()

                count += len(completed)
                failed_count += len(failed)

                # A whole batch failing is systemic (server down, bad model,
                # schema drift) -- bail rather than burn the retry budget one
                # expensive call at a time.
                if failed and not completed and work:
                    logger.error(
                        f"extract-llm: every file in the batch failed ({len(failed)}); stopping. "
                        f"Check the LLM server and the last error above."
                    )
                    aborted = True
                    break

                done = count + failed_count
                per_file = (time.monotonic() - started) / max(done, 1)
                eta_h = per_file * max(target - done, 0) / 3600
                pbar.set_postfix(failed=failed_count, mentions=mention_count, events=event_count, eta=f"{eta_h:.1f}h")
                pbar.update(len(completed) + len(failed))
                if eta_h > _WARN_ETA_HOURS and not warned_eta:
                    logger.warning(
                        f"extract-llm pace ~{per_file:.1f}s/file -> ~{eta_h:.0f}h for the {target - done:,} left. "
                        f"Consider a faster served model, higher --concurrency, or --limit."
                    )
                    warned_eta = True

    logger.success(
        f"Combined LLM pass: {mention_count} mentions, {relation_count} relations, {event_count} events "
        f"from {count} files ({failed_count} failed) in {(time.monotonic() - started) / 60:.1f} min"
    )
    return count
