"""Email extraction workflow.

Emails always go through pyparse -- its structured EmailMetadata (real
from/to/cc/state/labels) is richer than xberg's flat email parsing, and
extracting an email is also the only way to recover its attachments as
their own files. This is therefore a dedicated pipeline rather than one
more branch of extract_documents.py: each pending email is parsed once,
its own text/metadata is persisted, and its attachments are written to
disk and inserted into the `file` table with `parent_id` set to the email,
then queued for their own extraction -- so a later extract_documents_workflow
run picks them up and can batch them through xberg alongside everything else.
"""

from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING

import anyio
from loguru import logger

from cipher.datastores.postgres.repositories import (
    PostgresEnrichmentRepository,
    PostgresExtractedTextRepository,
    PostgresFileRepository,
)
from cipher.schemas.enrichment import EnrichableType, EnrichmentType
from cipher.schemas.extraction import ExtractedTextCreate, ExtractionContentFormat, TextExtractor
from cipher.schemas.file import FileBase, FileCreate
from cipher.utils.io import fetch_bytes_from_uri

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_ELIGIBLE_ATTACHMENT_GROUPS = frozenset({"document"})


async def _persist_attachment(
    session: "AsyncSession",
    attachment: FileBase,
    dataset_id: str,
    parent_id: str,
    eligible_attachment_groups: frozenset[str],
) -> None:
    """Insert an email attachment as its own file row and queue it for extraction if eligible."""
    if attachment.path is None or attachment.uri is None:
        # No payload was written to disk (e.g. parse_email was called without
        # extract_children=True) -- nothing to point a File row at.
        return

    file_repo = PostgresFileRepository(session=session)
    file_create = FileCreate(**attachment.model_dump(exclude={"parent_id"}), dataset_id=dataset_id, parent_id=parent_id)
    file = await file_repo.upsert_file(file_create)

    if file.filetype_group in eligible_attachment_groups:
        logger.debug(f"Queuing attachment {file.filename!r} ({file.id}) from email {parent_id} for extraction")
        enrichment_repo = PostgresEnrichmentRepository(session=session)
        await enrichment_repo.queue_enrichments_for_resource(
            enrichable_type=EnrichableType.FILE,
            enrichable_id=file.id,
            enrichment_types=[EnrichmentType.TEXT_EXTRACTION],
        )


async def _extract_email(
    session: "AsyncSession",
    file_resource: dict,
    eligible_attachment_groups: frozenset[str],
) -> ExtractedTextCreate:
    from functools import partial

    from pyparse.parsers.email import parse_email

    # logger.debug(f"Parsing email {file_resource['id']} ({file_resource['filename']!r})")
    data = await anyio.to_thread.run_sync(fetch_bytes_from_uri, file_resource["uri"])

    out_dir = Path(file_resource["path"]).parent / f"{Path(file_resource['path']).stem}_attachments"
    out_dir.mkdir(parents=True, exist_ok=True)

    email = await anyio.to_thread.run_sync(
        partial(parse_email, data, file_resource["filetype"], extract_children=True, out_dir=out_dir)
    )

    for attachment in email.attachments:
        if isinstance(attachment, FileBase):
            await _persist_attachment(
                session, attachment, file_resource["dataset_id"], file_resource["id"], eligible_attachment_groups
            )

    return ExtractedTextCreate(
        file_id=file_resource["id"],
        content=email.plain or email.html or "",
        content_format=ExtractionContentFormat.PLAIN,
        extractor=TextExtractor.PYPARSE,
        metadata=email.metadata,
    )


async def queue_email_extraction_enrichments(session: "AsyncSession", dataset_id: str) -> int:
    """Queue TEXT_EXTRACTION enrichments for a dataset's email files."""
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    count = await enrichment_repo.queue_enrichments_by_filter(
        dataset_id=dataset_id,
        enrichment_type=EnrichmentType.TEXT_EXTRACTION,
        filetype_group="email",
    )
    await session.commit()
    return count


async def extract_emails_workflow(
    session: "AsyncSession",
    dataset_id: str,
    eligible_attachment_groups: frozenset[str] = DEFAULT_ELIGIBLE_ATTACHMENT_GROUPS,
    batch_size: int = 20,
) -> int:
    """Extract text for a dataset's emails, persisting their attachments as files. Returns emails processed."""
    logger.debug(f"extract_emails_workflow starting for dataset {dataset_id}")
    await queue_email_extraction_enrichments(session=session, dataset_id=dataset_id)

    enrichment_repo = PostgresEnrichmentRepository(session=session)
    extracted_text_repo = PostgresExtractedTextRepository(session=session)

    start = perf_counter()
    count = 0

    while True:
        batch = await enrichment_repo.get_pending_batch(
            enrichment_type=EnrichmentType.TEXT_EXTRACTION,
            enrichable_type=EnrichableType.FILE,
            batch_size=batch_size,
            dataset_id=dataset_id,
            filetype_group_filter="email",
        )
        if not batch:
            break

        logger.debug(f"Processing batch of {len(batch)} pending emails")
        await enrichment_repo.mark_processing(enrichment_ids=[item.enrichment.id for item in batch])
        await session.commit()

        completed, failed = [], []
        for item in batch:
            try:
                result = await _extract_email(session, item.resource, eligible_attachment_groups)
                await extracted_text_repo.upsert(result)
                completed.append(item.enrichment.id)
            except Exception as e:
                logger.error(f"Email extraction failed for file {item.resource['id']}: {e}")
                await session.rollback()
                failed.append(item.enrichment.id)

        if completed:
            await enrichment_repo.mark_completed_batch(completed)
        if failed:
            await enrichment_repo.mark_failed_batch(failed, increment_retry=True)
        await session.commit()

        count += len(completed)
        logger.info(f"Extracted {len(completed)} emails ({count} total)")

    total_ms = int((perf_counter() - start) * 1000)
    logger.success(f"Extracted text for {count} emails in {total_ms}ms")
    return count
