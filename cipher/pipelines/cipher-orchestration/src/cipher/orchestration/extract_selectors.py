"""Selector extraction workflow (SELECTOR_EXTRACTION enrichment).

Scope for now: **email headers only**. Every participant on a parsed email
(`from` / `sender` / `to` / `cc` / `bcc`, held as `EmailMetadata` on the
email's `ExtractedText` row) becomes:

  * an `email` selector entity (deduped on `(dataset_id, email, normalized_value)`
    via the unique constraint -- `get_or_create_selector`), and
  * a `structured_field` mention of that address, already resolved to the
    selector entity (selectors resolve `by_value`, so no sweep is needed), with
    `field_path` = `header.from` / `header.to[1]` / ...
  * when the header also carries a display name, an *unresolved* `person`
    mention of that name in the same field -- `resolve-entities` (later) blocks
    on `normalized_value` to attach it to a real person.

The free-text pass (pyselectors regex over `ExtractedText.content` for phone /
IBAN / IMEI / passport) is a deliberate TODO -- see `_extract_text_selectors`.

Re-runnable: `queue_enrichments_by_filter` only queues emails without a
SELECTOR_EXTRACTION row, and a completed row is never revisited, so a second
run is a no-op until `reset-entities` clears them.
"""

from typing import TYPE_CHECKING

from loguru import logger
from tqdm import tqdm

from cipher.datastores.postgres.repositories import (
    PostgresEnrichmentRepository,
    PostgresEntityRepository,
    PostgresExtractedTextRepository,
    PostgresMentionRepository,
)
from cipher.datastores.postgres.utils import normalize_name
from cipher.schemas.content.email import EmailAddress, EmailMetadata
from cipher.schemas.graph.mention import MentionCreate, MentionedType
from cipher.schemas.graph.ontology import EntityType, SelectorKind
from cipher.schemas.ingestion.enrichment import EnrichableType, EnrichmentType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_EXTRACTOR = "email_headers"
_EMAIL_FILETYPE_GROUP = "email"


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


async def _extract_email_selectors(
    session: "AsyncSession",
    file_resource: dict,
    extracted_text_repo: PostgresExtractedTextRepository,
    entity_repo: PostgresEntityRepository,
) -> int:
    """Turn one email's header participants into selector entities + mentions. Returns mentions written."""
    from pyselectors.normalize import normalize_email

    file_id = file_resource["id"]
    dataset_id = file_resource["dataset_id"]

    extracted = await extracted_text_repo.get_by_file_id(file_id)
    if extracted is None or not isinstance(extracted.metadata, EmailMetadata):
        return 0

    mentions: list[MentionCreate] = []
    seen: set[tuple[str, str]] = set()

    for field_path, participant in _email_participants(extracted.metadata):
        normalized = normalize_email(participant.value)
        if not normalized or "@" not in normalized:
            continue
        if (field_path, normalized) in seen:
            continue
        seen.add((field_path, normalized))

        selector_entity, _ = await entity_repo.get_or_create_selector(
            dataset_id=dataset_id,
            selector_kind=SelectorKind.EMAIL,
            raw_value=participant.value,
            normalized_value=normalized,
            display_name=normalized,
        )

        mentions.append(
            MentionCreate(
                dataset_id=dataset_id,
                entity_id=selector_entity.id,
                mentioned_type=MentionedType.STRUCTURED_FIELD,
                mentioned_id=extracted.id,
                file_id=file_id,
                surface_text=f"{participant.name} <{participant.value}>" if participant.name else participant.value,
                entity_type=EntityType.SELECTOR,
                entity_attribute="value",
                selector_kind=SelectorKind.EMAIL,
                normalized_value=normalized,
                field_path=field_path,
                context=participant.name,
                extractor=_EXTRACTOR,
                extraction_confidence=1.0,
            )
        )

        if participant.name:
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
                    surface_text=participant.name,
                    entity_type=None,
                    entity_attribute="name",
                    normalized_value=normalize_name(participant.name),
                    field_path=field_path,
                    context=participant.value,
                    extractor=_EXTRACTOR,
                    extraction_confidence=1.0,
                )
            )

    mention_repo = PostgresMentionRepository(session=session)
    return await mention_repo.add_mentions_batch(mentions)


async def _extract_text_selectors(*args, **kwargs) -> int:
    """TODO: run `pyselectors.extract_selectors` over `ExtractedText.content`.

    Would cover phone / IBAN / IMEI / passport spans in document + email bodies,
    with real char offsets into `content`. Out of scope for the header-only pass.
    """
    raise NotImplementedError


async def queue_selector_extraction_enrichments(session: "AsyncSession", dataset_id: str) -> int:
    """Queue SELECTOR_EXTRACTION enrichments for a dataset's email files."""
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    count = await enrichment_repo.queue_enrichments_by_filter(
        dataset_id=dataset_id,
        enrichment_type=EnrichmentType.SELECTOR_EXTRACTION,
        filetype_group=_EMAIL_FILETYPE_GROUP,
    )
    await session.commit()
    return count


async def extract_selectors_workflow(
    session: "AsyncSession",
    dataset_id: str,
    batch_size: int = 50,
) -> int:
    """Extract email-header selectors for a dataset's emails. Returns emails processed.

    Run `extract-text` first -- this reads persisted `ExtractedText` rows (for
    their `EmailMetadata`), it doesn't parse `.eml`/`.msg` files itself.
    """
    await queue_selector_extraction_enrichments(session=session, dataset_id=dataset_id)

    enrichment_repo = PostgresEnrichmentRepository(session=session)
    extracted_text_repo = PostgresExtractedTextRepository(session=session)
    entity_repo = PostgresEntityRepository(session=session)

    total = await enrichment_repo.count_pending(
        enrichment_type=EnrichmentType.SELECTOR_EXTRACTION,
        enrichable_type=EnrichableType.FILE,
        dataset_id=dataset_id,
        filetype_group_filter=_EMAIL_FILETYPE_GROUP,
    )
    count = failed_count = mention_count = 0

    with tqdm(total=total, desc="Extracting selectors", unit=" email") as pbar:
        while True:
            batch = await enrichment_repo.get_pending_batch(
                enrichment_type=EnrichmentType.SELECTOR_EXTRACTION,
                enrichable_type=EnrichableType.FILE,
                batch_size=batch_size,
                dataset_id=dataset_id,
                filetype_group_filter=_EMAIL_FILETYPE_GROUP,
            )
            if not batch:
                break

            await enrichment_repo.mark_processing(enrichment_ids=[item.enrichment.id for item in batch])
            await session.commit()

            completed, failed = [], []
            for item in batch:
                try:
                    mention_count += await _extract_email_selectors(
                        session=session,
                        file_resource=item.resource,
                        extracted_text_repo=extracted_text_repo,
                        entity_repo=entity_repo,
                    )
                    completed.append(item.enrichment.id)
                except Exception as e:
                    logger.error(f"Selector extraction failed for file {item.resource['id']}: {e}")
                    await session.rollback()
                    failed.append(item.enrichment.id)

            if completed:
                await enrichment_repo.mark_completed_batch(completed)
            if failed:
                await enrichment_repo.mark_failed_batch(failed, increment_retry=True)
            await session.commit()

            count += len(completed)
            failed_count += len(failed)
            pbar.set_postfix(failed=failed_count, mentions=mention_count)
            pbar.update(len(completed) + len(failed))

    logger.success(f"Extracted {mention_count} selector mentions from {count} emails ({failed_count} failed)")
    return count


async def get_selector_extraction_stats(session: "AsyncSession", dataset_id: str | None = None) -> dict:
    """Enrichment stats for selector extraction."""
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    return await enrichment_repo.get_enrichment_stats(
        enrichable_type=EnrichableType.FILE,
        dataset_id=dataset_id,
        enrichment_type=EnrichmentType.SELECTOR_EXTRACTION,
    )
