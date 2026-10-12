"""Email extraction workflow.

Emails always go through pyparse -- its structured EmailMetadata (real
from/to/cc/state/labels) is richer than xberg's flat email parsing, and
extracting an email is also the only way to recover its attachments as
their own files. This is therefore a dedicated pipeline rather than one
more branch of extract_documents.py: each pending email is parsed once,
its own text/metadata is persisted, and its attachments go into the output
store (through pyparse's child sink) and the `file` table with `parent_id`
set to the email and `path` where they were found (`<email path>/<name>`),
then are queued for their own extraction -- so a later extract_documents_workflow
run picks them up and can batch them through xberg alongside everything else.

Tried thread-pool-parallelizing the parse step across a batch (the same
pattern embed_images.py/detect_faces.py use for their CPU-bound work), but
benchmarked measurably *slower* (~20% on a real ~1600-email corpus) than
the plain sequential loop below. `email`/MIME parsing is pure Python and
holds the GIL almost continuously, so threads add scheduling/GIL-contention
overhead without buying real parallelism -- unlike hashing or ONNX
inference, which release the GIL for large enough inputs. Kept sequential.
"""

from collections import Counter
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

import anyio
from loguru import logger
from sqlalchemy import update
from tqdm import tqdm

from cipher.datastores.postgres.repositories import (
    PostgresEnrichmentRepository,
    PostgresExtractedTextRepository,
    PostgresFileRepository,
)
from cipher.datastores.postgres.tables.file import FileTable
from cipher.orchestration.settings import output_store
from cipher.schemas.content.email import EmailBase
from cipher.schemas.content.extraction import ExtractedTextCreate, ExtractionContentFormat, TextExtractor
from cipher.schemas.ingestion.enrichment import EnrichableType, EnrichmentType
from cipher.schemas.ingestion.file import FileBase, FileCreate
from cipher.utils.output import OutputStore
from cipher.utils.uri import read_bytes

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# An attached email is extracted as an email of its own.
DEFAULT_ELIGIBLE_ATTACHMENT_GROUPS = frozenset({"document", "email"})


async def _persist_attachment(
    session: "AsyncSession",
    attachment: FileBase,
    dataset_id: str,
    parent_id: str,
    eligible_attachment_groups: frozenset[str],
) -> None:
    """Insert an email attachment as its own file row and queue it for extraction if eligible."""
    if attachment.path is None or attachment.uri is None:
        logger.warning(f"Attachment {attachment.filename!r} of file {parent_id} was not stored; no row made")
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


class _BlobSink:
    """One email's child files into the output store; each `path` is where it was found, `<email path>/<name>`."""

    def __init__(self, *, store: OutputStore, parent_path: str) -> None:
        self.store, self.prefix = store, parent_path.rstrip("/") + "/"
        self.seen: Counter[str] = Counter()
        self.stored: list[FileBase] = []

    def __call__(self, *, data: bytes, filename: str | None) -> FileBase:
        """Store the bytes, type them, and name the child uniquely within its email."""
        from pyparse.children import describe

        child = describe(data=data, filename=filename)
        with self.store.writer() as writer:
            writer.write(data)
            stored = writer.commit()
        child = child.model_copy(update={"uri": stored.uri, "path": self.prefix + self._unique(filename)})
        self.stored.append(child)
        return child

    def _unique(self, filename: str | None) -> str:
        """The name, or `attachment`, with `~2`, `~3` ... before the extension when it repeats."""
        name = (filename or "attachment").replace("/", "_").strip() or "attachment"
        self.seen[name] += 1
        if (n := self.seen[name]) == 1:
            return name
        stem, suffix = PurePosixPath(name).stem, PurePosixPath(name).suffix
        return f"{stem}~{n}{suffix}"


async def _extract_email(
    session: "AsyncSession",
    file_resource: dict,
    eligible_attachment_groups: frozenset[str],
    store: OutputStore,
    save_inline_images: bool = True,
) -> ExtractedTextCreate:
    from functools import partial

    from pyparse.parsers.email import EmailOptions, parse_email
    from pyparse.parsers.email.quotes import find_quoted_blocks
    from pyparse.parsers.text import html_to_text

    data = await anyio.to_thread.run_sync(read_bytes, file_resource["uri"])
    sink = _BlobSink(store=store, parent_path=file_resource["path"])
    email: EmailBase = await anyio.to_thread.run_sync(
        partial(
            parse_email,
            data,
            filetype=file_resource["filetype"],
            sink=sink,
            options=EmailOptions(save_inline_images=save_inline_images),
        )
    )

    if email.is_encrypted != bool(file_resource.get("is_encrypted")):  # the parser knows best (.msg message class)
        await session.execute(
            update(FileTable).where(FileTable.id == file_resource["id"]).values(is_encrypted=email.is_encrypted)
        )

    # every child the sink stored -- attachments, and (when saved) images the body shows
    for attachment in sink.stored:
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
    content = (html_to_text(email.html) if email.html else "") or email.plain or ""

    return ExtractedTextCreate(
        file_id=file_resource["id"],
        content=content,
        content_format=ExtractionContentFormat.PLAIN,
        extractor=TextExtractor.PYPARSE,
        metadata=email.metadata.model_copy(update={"quoted_blocks": find_quoted_blocks(content)}),
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
    store: OutputStore | None = None,
    save_inline_images: bool = True,
) -> int:
    """Extract text for a dataset's emails, storing their attachments as files found in them. Returns emails processed.

    With `save_inline_images`, images their bodies show are stored the same way (never as attachments).
    Attachment bytes go into `store` (default: the dataset's output store, `<OUTPUT_URI>/<dataset_id>/`).
    """
    store = store or output_store(dataset_id=dataset_id)
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

            completed: list[str] = []
            failed: dict[str, str | Exception] = {}
            for item in batch:
                try:
                    result = await _extract_email(
                        session=session,
                        file_resource=item.resource,
                        eligible_attachment_groups=eligible_attachment_groups,
                        store=store,
                        save_inline_images=save_inline_images,
                    )
                    await extracted_text_repo.upsert(result)
                    completed.append(item.enrichment.id)
                except Exception as e:
                    logger.error(f"Email extraction failed for file {item.resource['id']}: {e}")
                    await session.rollback()
                    failed[item.enrichment.id] = e

            if completed:
                await enrichment_repo.mark_completed_batch(completed)
            await enrichment_repo.mark_failed(failed)
            await session.commit()

            count += len(completed)
            failed_count += len(failed)
            pbar.set_postfix(failed=failed_count)
            pbar.update(len(completed) + len(failed))

    logger.success(f"Extracted text for {count} emails ({failed_count} failed)")
    return count
