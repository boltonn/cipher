"""Selector extraction workflow (SELECTOR_EXTRACTION enrichment).

Two passes per file, both writing `mention` rows that are already resolved to a
`selector` entity (selectors resolve `by_value`, so no sweep is needed):

  * **email headers** (`EmailMetadata` on the `ExtractedText` row) -- every
    `from` / `sender` / `to` / `cc` / `bcc` participant becomes an `email`
    selector + a `structured_field` mention with `field_path` = `header.from` /
    `header.to[1]` / ..., plus an *unresolved* untyped name mention for any
    display name (for the Review queue).

  * **free text** (`ExtractedText.content`) -- `pyselectors.extract_selectors`
    over the body: phone / email / ip / iban / imei / crypto / social-handle
    spans with real char offsets into `content`, kind attributes, and a
    context-scored confidence. Uses `DocumentMetadata.detected_language` as the
    language hint.

Re-runnable: `queue_enrichments_by_filter` only queues files without a
SELECTOR_EXTRACTION row, and a completed row is never revisited, so a second
run is a no-op until `reset-entities` clears them (or `--rescan` requeues them).
A file whose header mentions exist keeps them; the body pass is additive -- it
only writes spans the earlier run didn't, so a rescan fills gaps without
duplicating (or discarding Review decisions).
"""

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from loguru import logger
from tqdm import tqdm

from cipher.datastores.postgres.repositories import (
    PostgresEnrichmentRepository,
    PostgresEntityRepository,
    PostgresExtractedTextRepository,
    PostgresLocationRepository,
    PostgresMentionRepository,
)
from cipher.datastores.postgres.utils import normalize_name
from cipher.schemas.content.document import DocumentMetadata
from cipher.schemas.content.email import EmailAddress, EmailMetadata
from cipher.schemas.content.text_correction import correction_filter
from cipher.schemas.graph.location import LocationCreate
from cipher.schemas.graph.mention import MentionCreate, MentionedType
from cipher.schemas.graph.ontology import EntityType, LocationSource, SelectorType
from cipher.schemas.ingestion.enrichment import (
    DEFAULT_FILETYPE_GROUPS,
    TEXT_NATIVE_GROUPS,
    EnrichableType,
    EnrichmentType,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_HEADER_EXTRACTOR = "email_headers"
_TEXT_EXTRACTOR = "selectors"
_TEXT_CONTEXT_WINDOW = 80


def _email_participants(metadata: EmailMetadata) -> list[tuple[str, EmailAddress]]:
    """Pair every header participant with its dotted `field_path`."""
    pairs: list[tuple[str, EmailAddress]] = []
    if metadata.sent_from is not None:
        pairs.append(("header.from", metadata.sent_from))
    if metadata.sender is not None:
        pairs.append(("header.sender", metadata.sender))
    for index, participant in enumerate(metadata.sent_to):
        pairs.append((f"header.to[{index}]", participant))
    for index, participant in enumerate(metadata.cc):
        pairs.append((f"header.cc[{index}]", participant))
    for index, participant in enumerate(metadata.bcc):
        pairs.append((f"header.bcc[{index}]", participant))
    return pairs


async def _resolve_selector(
    cache: dict[tuple, str],
    entity_repo: PostgresEntityRepository,
    *,
    dataset_id: str,
    selector_type: SelectorType,
    normalized_value: str,
    raw_value: str,
    selector_subtype=None,
    region_hint: str | None = None,
    attributes: dict[str, str] | None = None,
) -> str:
    """Resolve a selector via a per-run cache.

    A value recurring across thousands of files (quoted reply chains) is looked
    up once, not once per file.
    """
    key = (dataset_id, selector_type, normalized_value)
    hit = cache.get(key)
    if hit is not None:
        return hit
    entity, _ = await entity_repo.get_or_create_selector(
        dataset_id=dataset_id,
        selector_type=selector_type,
        selector_subtype=selector_subtype,
        raw_value=raw_value,
        normalized_value=normalized_value,
        region_hint=region_hint,
        display_name=normalized_value,
        attributes=attributes,
    )
    cache[key] = entity.id
    return entity.id


async def _extract_file_selectors(
    session: "AsyncSession",
    file_resource: dict,
    extracted_text_repo: PostgresExtractedTextRepository,
    entity_repo: PostgresEntityRepository,
    selector_cache: dict[tuple, str],
) -> int:
    """Run both selector passes over one file. Returns the number of mentions written."""
    file_id = file_resource["id"]
    dataset_id = file_resource["dataset_id"]

    extracted = await extracted_text_repo.get_by_file_id(file_id)
    if extracted is None:
        return 0

    mention_repo = PostgresMentionRepository(session=session)
    location_repo = PostgresLocationRepository(session=session)
    written = 0
    has_header_mentions = await mention_repo.has_extractor_mentions(
        mentioned_id=extracted.id, extractor=_HEADER_EXTRACTOR
    )
    if isinstance(extracted.metadata, EmailMetadata) and not has_header_mentions:
        written += await _extract_email_selectors(
            dataset_id=dataset_id,
            file_id=file_id,
            extracted=extracted,
            entity_repo=entity_repo,
            mention_repo=mention_repo,
            selector_cache=selector_cache,
        )
    existing_offsets = await mention_repo.extractor_offsets(mentioned_id=extracted.id, extractor=_TEXT_EXTRACTOR)
    keep = (
        correction_filter(
            corrected_ranges=extracted.corrected_ranges or [],
            taken=await mention_repo.text_spans(mentioned_id=extracted.id),
        )
        if extracted.is_content_corrected
        else None
    )
    written += await _extract_text_selectors(
        dataset_id=dataset_id,
        file_id=file_id,
        extracted=extracted,
        entity_repo=entity_repo,
        mention_repo=mention_repo,
        selector_cache=selector_cache,
        skip_offsets=existing_offsets,
        keep=keep,
    )
    if not existing_offsets or keep is not None:
        written += await _extract_text_coordinates(
            dataset_id=dataset_id,
            file_id=file_id,
            extracted=extracted,
            mention_repo=mention_repo,
            location_repo=location_repo,
            keep=keep,
        )
    return written


async def _extract_email_selectors(
    *,
    dataset_id: str,
    file_id: str,
    extracted,
    entity_repo: PostgresEntityRepository,
    mention_repo: PostgresMentionRepository,
    selector_cache: dict[tuple, str],
) -> int:
    """Turn one email's header participants into selector entities + mentions."""
    from pyselectors.normalize import normalize_email

    mentions: list[MentionCreate] = []
    seen: set[tuple[str, str]] = set()

    for field_path, participant in _email_participants(extracted.metadata):
        normalized = normalize_email(participant.value)
        if not normalized or "@" not in normalized:
            continue
        if (field_path, normalized) in seen:
            continue
        seen.add((field_path, normalized))

        selector_entity_id = await _resolve_selector(
            selector_cache,
            entity_repo,
            dataset_id=dataset_id,
            selector_type=SelectorType.EMAIL,
            normalized_value=normalized,
            raw_value=participant.value,
        )

        mentions.append(
            MentionCreate(
                dataset_id=dataset_id,
                entity_id=selector_entity_id,
                mentioned_type=MentionedType.STRUCTURED_FIELD,
                mentioned_id=extracted.id,
                file_id=file_id,
                surface_text=f"{participant.name.strip()} <{participant.value}>"
                if participant.name and participant.name.strip()
                else participant.value,
                entity_type=EntityType.SELECTOR,
                entity_attribute="value",
                selector_type=SelectorType.EMAIL,
                normalized_value=normalized,
                field_path=field_path,
                context=participant.name.strip() if participant.name else None,
                extractor=_HEADER_EXTRACTOR,
                extraction_confidence=1.0,
            )
        )

        if name := (participant.name or "").strip():
            # A display name on an address is an actor name of unknown kind --
            # "Nick Bolton" and "Medium Daily Digest" are indistinguishable here.
            # Leave entity_type null so it lands in Review as an untyped name for
            # an analyst (or a later NER pass) to call person vs organization,
            # rather than silently minting a wrong `person`.
            mentions.append(
                MentionCreate(
                    dataset_id=dataset_id,
                    entity_id=None,
                    mentioned_type=MentionedType.STRUCTURED_FIELD,
                    mentioned_id=extracted.id,
                    file_id=file_id,
                    surface_text=name,
                    entity_type=None,
                    entity_attribute="name",
                    normalized_value=normalize_name(name),
                    field_path=field_path,
                    context=participant.value,
                    extractor=_HEADER_EXTRACTOR,
                    extraction_confidence=1.0,
                )
            )

    return await mention_repo.add_mentions_batch(mentions)


def _context_snippet(content: str, start: int, end: int) -> str:
    """A newline-collapsed window around a span, mirroring extract_entities."""
    lo = max(0, start - _TEXT_CONTEXT_WINDOW)
    hi = min(len(content), end + _TEXT_CONTEXT_WINDOW)
    return content[lo:hi].replace("\n", " ").strip()


def _span_to_mention(
    span, *, dataset_id: str, file_id: str, extracted_id: str, content: str, entity_id: str | None = None
) -> MentionCreate:
    """Map one `SelectorSpan` to a resolved selector mention (pure; no DB)."""
    return MentionCreate(
        dataset_id=dataset_id,
        entity_id=entity_id,
        mentioned_type=MentionedType.EXTRACTED_TEXT,
        mentioned_id=extracted_id,
        file_id=file_id,
        surface_text=span.raw_value,
        entity_type=EntityType.SELECTOR,
        entity_attribute="value",
        selector_type=span.selector_type,
        selector_subtype=span.selector_subtype,
        normalized_value=span.normalized_value,
        start_offset=span.start_offset,
        end_offset=span.end_offset,
        context=_context_snippet(content, span.start_offset, span.end_offset),
        extractor=_TEXT_EXTRACTOR,
        extraction_confidence=span.confidence,
    )


async def _extract_text_selectors(
    *,
    dataset_id: str,
    file_id: str,
    extracted,
    entity_repo: PostgresEntityRepository,
    mention_repo: PostgresMentionRepository,
    selector_cache: dict[tuple, str],
    types: set[SelectorType] | None = None,
    skip_offsets: set[tuple[str | None, int]] | None = None,
    keep: Callable[[int, int], bool] | None = None,
) -> int:
    """Run `pyselectors.extract_selectors` over `ExtractedText.content` (only ``types``, when given).

    Spans whose ``(selector_type, start_offset)`` is in ``skip_offsets`` (already written
    by an earlier run) are skipped, so a re-scan only adds what that run missed; so are
    spans ``keep`` rejects (a corrected text: `correction_filter`).

    Offsets are char positions into `content`, the same contract NER uses.
    `DocumentMetadata.detected_language` seeds the context lexicon and phone
    region. Selector mentions are written already resolved (selectors resolve
    `by_value`), tagged `extractor="selectors"` -> `MentionProvenance.PATTERN`.
    """
    import asyncio

    from pyselectors import extract_selectors

    content = extracted.content or ""
    if not content.strip():
        return 0

    language = extracted.metadata.detected_language if isinstance(extracted.metadata, DocumentMetadata) else None
    spans = await asyncio.to_thread(extract_selectors, content, language=language, types=types)
    if not spans:
        return 0

    mentions: list[MentionCreate] = []
    seen = set(skip_offsets or ())
    for span in spans:
        key = (span.selector_type, span.start_offset)
        if key in seen or (keep is not None and not keep(span.start_offset, span.end_offset)):
            continue
        seen.add(key)
        selector_entity_id = await _resolve_selector(
            selector_cache,
            entity_repo,
            dataset_id=dataset_id,
            selector_type=span.selector_type,
            selector_subtype=span.selector_subtype,
            normalized_value=span.normalized_value,
            raw_value=span.raw_value,
            region_hint=span.region_hint,
            attributes=span.attributes or None,
        )
        mentions.append(
            _span_to_mention(
                span,
                dataset_id=dataset_id,
                file_id=file_id,
                extracted_id=extracted.id,
                content=content,
                entity_id=selector_entity_id,
            )
        )

    return await mention_repo.add_mentions_batch(mentions)


async def _extract_text_coordinates(
    *,
    dataset_id: str,
    file_id: str,
    extracted,
    mention_repo: PostgresMentionRepository,
    location_repo: PostgresLocationRepository,
    keep: Callable[[int, int], bool] | None = None,
) -> int:
    """Pull lat/long out of `ExtractedText.content` -> `location` points + LOCATION mentions.

    Coordinates are an NER-style output: each one becomes an *unresolved*
    `LOCATION` mention (`entity_attribute="coordinate"`, shows on the file text
    view, searchable) plus a `location` row (`source="coordinate_mention"`) so the
    point lands on the map. Re-run safe: the file's `coordinate_mention` points are
    replaced wholesale. On a corrected text (``keep``) the points are replaced even when
    none are left, and mentions are only added where ``keep`` allows.
    """
    import asyncio

    from pyselectors import extract_coordinates

    content = extracted.content or ""
    if not content.strip():
        return 0

    language = extracted.metadata.detected_language if isinstance(extracted.metadata, DocumentMetadata) else None
    coords = await asyncio.to_thread(extract_coordinates, content, language=language)
    if not coords and keep is None:
        return 0  # skip the per-file DELETE when there is nothing to write

    await location_repo.replace_file_locations(
        file_id=file_id,
        source=LocationSource.COORDINATE_MENTION,
        rows=[
            LocationCreate(
                file_id=file_id,
                dataset_id=dataset_id,
                latitude=c.latitude,
                longitude=c.longitude,
                source=LocationSource.COORDINATE_MENTION,
                source_id=f"{c.latitude:.6f},{c.longitude:.6f}",
                attributes={"format": c.coordinate_format, "raw": c.raw_value[:120]},
            )
            for c in coords
        ],
    )

    mentions = [
        MentionCreate(
            dataset_id=dataset_id,
            entity_id=None,
            mentioned_type=MentionedType.EXTRACTED_TEXT,
            mentioned_id=extracted.id,
            file_id=file_id,
            surface_text=c.raw_value,
            entity_type=EntityType.LOCATION,
            entity_attribute="coordinate",
            normalized_value=f"{c.latitude:.6f},{c.longitude:.6f}",
            start_offset=c.start_offset,
            end_offset=c.end_offset,
            context=_context_snippet(content, c.start_offset, c.end_offset),
            extractor=_TEXT_EXTRACTOR,
            extraction_confidence=c.confidence,
        )
        for c in coords
        if keep is None or keep(c.start_offset, c.end_offset)
    ]
    return await mention_repo.add_mentions_batch(mentions)


async def queue_selector_extraction_enrichments(
    session: "AsyncSession",
    dataset_id: str,
    filetype_groups: Sequence[str] = DEFAULT_FILETYPE_GROUPS[EnrichmentType.SELECTOR_EXTRACTION],
) -> int:
    """Queue SELECTOR_EXTRACTION enrichments for the dataset's files in `filetype_groups` (tables only when listed)."""
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    count = 0
    for group in filetype_groups:
        queue = (
            enrichment_repo.queue_enrichments_by_filter
            if group in TEXT_NATIVE_GROUPS
            else enrichment_repo.queue_files_with_text
        )
        count += await queue(
            dataset_id=dataset_id, enrichment_type=EnrichmentType.SELECTOR_EXTRACTION, filetype_group=group
        )
    await session.commit()
    return count


async def extract_selectors_workflow(
    session: "AsyncSession",
    dataset_id: str,
    batch_size: int = 50,
    filetype_groups: Sequence[str] = DEFAULT_FILETYPE_GROUPS[EnrichmentType.SELECTOR_EXTRACTION],
    rescan: bool = False,
) -> int:
    """Extract selectors (email headers + free-text) for every text-bearing file. Returns files processed.

    Run `extract-text` first -- this reads persisted `ExtractedText` rows, it
    doesn't parse source files itself. ``rescan`` revisits already-processed files,
    adding only the body spans their earlier run missed.
    """
    await queue_selector_extraction_enrichments(session=session, dataset_id=dataset_id, filetype_groups=filetype_groups)
    if rescan:
        from sqlalchemy import select

        from cipher.datastores.postgres.tables.file import FileTable

        file_ids = list(
            (await session.execute(select(FileTable.id).where(FileTable.dataset_id == dataset_id))).scalars()
        )
        requeue = PostgresEnrichmentRepository(session=session).requeue
        requeued = 0
        for start in range(0, len(file_ids), 10_000):
            requeued += await requeue(file_ids[start : start + 10_000], EnrichmentType.SELECTOR_EXTRACTION)
        await session.commit()
        logger.info(f"Requeued {requeued} files for a selector rescan")

    enrichment_repo = PostgresEnrichmentRepository(session=session)
    extracted_text_repo = PostgresExtractedTextRepository(session=session)
    entity_repo = PostgresEntityRepository(session=session)

    total = await enrichment_repo.count_pending(
        enrichment_type=EnrichmentType.SELECTOR_EXTRACTION,
        enrichable_type=EnrichableType.FILE,
        dataset_id=dataset_id,
    )
    count = failed_count = mention_count = 0
    selector_cache: dict[tuple, str] = {}

    with tqdm(total=total, desc="Extracting selectors", unit=" file") as pbar:
        while True:
            batch = await enrichment_repo.get_pending_batch(
                enrichment_type=EnrichmentType.SELECTOR_EXTRACTION,
                enrichable_type=EnrichableType.FILE,
                batch_size=batch_size,
                dataset_id=dataset_id,
            )
            if not batch:
                break

            await enrichment_repo.mark_processing(enrichment_ids=[item.enrichment.id for item in batch])
            await session.commit()

            completed, failed = [], {}
            for item in batch:
                try:
                    mention_count += await _extract_file_selectors(
                        session=session,
                        file_resource=item.resource,
                        extracted_text_repo=extracted_text_repo,
                        entity_repo=entity_repo,
                        selector_cache=selector_cache,
                    )
                    completed.append(item.enrichment.id)
                except Exception as e:
                    logger.error(f"Selector extraction failed for file {item.resource['id']}: {e}")
                    await session.rollback()
                    # a rollback drops uncommitted entities the cache now points at
                    selector_cache.clear()
                    failed[item.enrichment.id] = e

            if completed:
                await enrichment_repo.mark_completed_batch(completed)
            await enrichment_repo.mark_failed(failed)
            await session.commit()

            count += len(completed)
            failed_count += len(failed)
            pbar.set_postfix(failed=failed_count, mentions=mention_count)
            pbar.update(len(completed) + len(failed))

    from cipher.orchestration.domain_links import link_domain_selectors

    linked = await link_domain_selectors(session, dataset_id)
    logger.success(
        f"Extracted {mention_count} selector mentions from {count} files ({failed_count} failed); "
        f"linked {linked} websites to organizations"
    )
    return count


async def get_selector_extraction_stats(session: "AsyncSession", dataset_id: str | None = None) -> dict:
    """Enrichment stats for selector extraction."""
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    return await enrichment_repo.get_enrichment_stats(
        enrichable_type=EnrichableType.FILE,
        dataset_id=dataset_id,
        enrichment_type=EnrichmentType.SELECTOR_EXTRACTION,
    )
