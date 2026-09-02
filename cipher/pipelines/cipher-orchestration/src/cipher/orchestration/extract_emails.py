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

Tried thread-pool-parallelizing the parse step across a batch (the same
pattern embed_images.py/detect_faces.py use for their CPU-bound work), but
benchmarked measurably *slower* (~20% on a real ~1600-email corpus) than
the plain sequential loop below. `email`/MIME parsing is pure Python and
holds the GIL almost continuously, so threads add scheduling/GIL-contention
overhead without buying real parallelism -- unlike hashing or ONNX
inference, which release the GIL for large enough inputs. Kept sequential.
"""

from pathlib import Path
from typing import TYPE_CHECKING

import anyio
from loguru import logger
from tqdm import tqdm

from cipher.datastores.postgres.repositories import (
    PostgresEnrichmentRepository,
    PostgresExtractedTextRepository,
    PostgresFileRepository,
)
from cipher.schemas.content.email import EmailBase
from cipher.schemas.content.extraction import ExtractedTextCreate, ExtractionContentFormat, TextExtractor
from cipher.schemas.ingestion.enrichment import EnrichableType, EnrichmentType
from cipher.schemas.ingestion.file import FileBase, FileCreate
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
        enrichment_repo = PostgresEnrichmentRepository(session=session)
        await enrichment_repo.queue_enrichments_for_resource(
            enrichable_type=EnrichableType.FILE,
            enrichable_id=file.id,
            enrichment_types=[EnrichmentType.TEXT_EXTRACTION],
        )


def _attachments_out_dir(file_resource: dict, attachments_dir: Path | None) -> Path:
    """Where to write this email's attachment payloads.

    Defaults to a sibling `<stem>_attachments` directory next to the source
    file (the original behavior). Passing `attachments_dir` keeps attachments
    out of the source tree entirely, grouped by file ID under that root
    instead -- useful for local directories you don't want mutated, or to
    keep extracted payloads on a separate device/volume from the source.
    """
    if attachments_dir is not None:
        return attachments_dir / file_resource["id"]
    source_path = Path(file_resource["path"])
    return source_path.parent / f"{source_path.stem}_attachments"


async def _extract_email(
    session: "AsyncSession",
    file_resource: dict,
    eligible_attachment_groups: frozenset[str],
    attachments_dir: Path | None = None,
) -> ExtractedTextCreate:
    from functools import partial

    from pyparse.parsers.email import parse_email
    from pyparse.parsers.text import HtmlParser

    data = await anyio.to_thread.run_sync(fetch_bytes_from_uri, file_resource["uri"])

    out_dir = _attachments_out_dir(file_resource, attachments_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    email: EmailBase = await anyio.to_thread.run_sync(
        partial(parse_email, data, file_resource["filetype"], extract_children=True, out_dir=out_dir)
    )

    for attachment in email.attachments:
        if isinstance(attachment, FileBase):
            await _persist_attachment(
                session=session,
                attachment=attachment,
                dataset_id=file_resource["dataset_id"],
                parent_id=file_resource["id"],
                eligible_attachment_groups=eligible_attachment_groups,
            )

    # The HTML body, stripped to plain text, is the preferred content: it's
    # usually the richer/authoritative part (multipart emails often carry a
    # degraded text/plain sibling), and persisting raw markup would waste the
    # embedding token budget and pollute search results with tags. The plain
    # part is only a fallback for emails with no HTML body at all.
    content = (HtmlParser.to_text(email.html) if email.html else "") or email.plain or ""

    return ExtractedTextCreate(
        file_id=file_resource["id"],
        content=content,
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
    attachments_dir: Path | None = None,
) -> int:
    """Extract text for a dataset's emails, persisting their attachments as files. Returns emails processed.

    `attachments_dir`, if set, roots every email's extracted attachments
    under `attachments_dir/<file_id>/` instead of a sibling directory next
    to the source `.eml`/`.msg` file -- see `_attachments_out_dir`.
    """
    await queue_email_extraction_enrichments(session=session, dataset_id=dataset_id)

    enrichment_repo = PostgresEnrichmentRepository(session=session)
    extracted_text_repo = PostgresExtractedTextRepository(session=session)

    total = await enrichment_repo.count_pending(
        enrichment_type=EnrichmentType.TEXT_EXTRACTION,
        enrichable_type=EnrichableType.FILE,
        dataset_id=dataset_id,
        filetype_group_filter="email",
    )
    count = failed_count = 0

    with tqdm(total=total, desc="Extracting emails", unit=" email") as pbar:
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

            await enrichment_repo.mark_processing(enrichment_ids=[item.enrichment.id for item in batch])
            await session.commit()

            completed, failed = [], []
            for item in batch:
                try:
                    result = await _extract_email(
                        session=session,
                        file_resource=item.resource,
                        eligible_attachment_groups=eligible_attachment_groups,
                        attachments_dir=attachments_dir,
                    )
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
            failed_count += len(failed)
            pbar.set_postfix(failed=failed_count)
            pbar.update(len(completed) + len(failed))

    logger.success(f"Extracted text for {count} emails ({failed_count} failed)")
    return count
