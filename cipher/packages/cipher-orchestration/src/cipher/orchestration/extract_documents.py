"""Document text extraction workflow, batched via xberg.

Unlike emails (see extract_emails.py), there's no richer alternative parser
to choose between for documents, so this pipeline always uses xberg -- and
hands whole batches of pending files to `batch_extract_files_sync` in one
call rather than looping one file at a time, leveraging xberg's own
internal parallelism across the batch. Running extract_emails_workflow
first means any email attachments it persisted (with filetype_group
"document") are already real `file` rows by the time this runs, so they
get swept up in the same batch as everything else -- no special-casing.
"""

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING, Any

import anyio
from loguru import logger

from cipher.datastores.postgres.repositories import (
    PostgresEnrichmentRepository,
    PostgresExtractedTextRepository,
)
from cipher.schemas.detection import BoundingBox
from cipher.schemas.document import DocumentMetadata, DocumentStructureNode, ExtractedTableInfo
from cipher.schemas.email import EmailMetadata
from cipher.schemas.enrichment import EnrichableType, EnrichmentType
from cipher.schemas.extraction import ExtractedTextCreate, ExtractionContentFormat, PrechunkedSpan, TextExtractor

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# Shared with embed_text.py's CLIR chunker -- both take this as their
# `chunk_size` default so chunk boundaries don't drift depending on which
# chunker produced them for otherwise-similar documents.
DEFAULT_CHUNK_SIZE = 512


class Chunker(StrEnum):
    """Which chunker splits a document's extracted text into embeddable pieces.

    KREUZBERG produces chunks as part of the same xberg extraction call, not
    a separate pass. CLIR is the alternative, applied as a later stage
    (embed_text.py).
    """

    KREUZBERG = "kreuzberg"
    CLIR = "clir"


def _parse_xberg_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _normalize_bbox(raw: dict | None, page_width: float | None, page_height: float | None) -> BoundingBox | None:
    """Convert xberg's raw point-coordinate bbox into the project's shared [0, 1] `BoundingBox`.

    xberg reports x0/y0/x1/y1 in absolute page points; every other detector
    (face, object) in this codebase reports xmin/ymin/xmax/ymax normalized to
    [0, 1], so extraction conforms to that standard rather than adding a
    second bounding-box shape.
    """
    if not raw or not page_width or not page_height:
        return None
    return BoundingBox(
        xmin=max(0.0, min(1.0, raw["x0"] / page_width)),
        ymin=max(0.0, min(1.0, raw["y0"] / page_height)),
        xmax=max(0.0, min(1.0, raw["x1"] / page_width)),
        ymax=max(0.0, min(1.0, raw["y1"] / page_height)),
    )


def _prechunked_from_kreuzberg(chunks: list) -> list[PrechunkedSpan]:
    spans = []
    for chunk in chunks:
        heading_context = chunk.metadata.get("heading_context")
        heading_path = (
            [h["text"] for h in heading_context["headings"]] if heading_context else None
        )
        spans.append(
            PrechunkedSpan(
                content=chunk.content,
                start_offset=chunk.metadata.get("byte_start", 0),
                end_offset=chunk.metadata.get("byte_end", 0),
                heading_path=heading_path,
                token_count=chunk.metadata.get("token_count"),
                first_page=chunk.metadata.get("first_page"),
                last_page=chunk.metadata.get("last_page"),
            )
        )
    return spans


def _document_structure_from_kreuzberg(
    document: dict | None, page_width: float | None, page_height: float | None
) -> list[DocumentStructureNode] | None:
    """Project xberg's DocumentStructure nodes down to what a highlight UI needs."""
    if not document:
        return None
    nodes = []
    for node in document.get("nodes", []):
        content = node.get("content") or {}
        nodes.append(
            DocumentStructureNode(
                id=node["id"],
                node_type=content.get("node_type", "unknown"),
                text=content.get("text"),
                parent=node.get("parent"),
                page=node.get("page"),
                page_end=node.get("page_end"),
                bounding_box=_normalize_bbox(node.get("bbox"), page_width, page_height),
            )
        )
    return nodes or None


def _run_batch(
    paths: list[str], use_chunking: bool, tokenizer_model_dir: Path | None, chunk_size: int
) -> "list[Any]":
    """CPU-bound worker: xberg's batched extraction call, run off the event loop."""
    from xberg import ChunkingConfig, ExtractionConfig, HierarchyConfig, PdfConfig, batch_extract_files_sync

    chunking = None
    if use_chunking:
        chunking = ChunkingConfig(
            chunker_type="markdown",
            sizing_type="tokenizer" if tokenizer_model_dir else "characters",
            sizing_model=str(tokenizer_model_dir) if tokenizer_model_dir else None,
            # max_chars is xberg's one size knob regardless of sizing_type --
            # tokens when sizing_type="tokenizer", characters otherwise. Kept
            # equal to embed_text.py's CLIR chunk_size so chunk boundaries
            # don't drift depending on which chunker produced them.
            max_chars=chunk_size,
            prepend_heading_context=True,
        )
    # include_document_structure is cheap and gives real per-node page + bounding
    # box data (result.document["nodes"]) for "highlight this in the original
    # document" UI. PDF hierarchy detection is what actually populates node
    # bounding boxes for PDFs.
    config = ExtractionConfig(
        chunking=chunking,
        include_document_structure=True,
        pdf_options=PdfConfig(hierarchy=HierarchyConfig(include_bbox=True)),
    )
    return batch_extract_files_sync(paths, config=config)


def _build_extracted_text(
    file_resource: dict, result: "Any", use_chunking: bool, parent_email_metadata: EmailMetadata | None
) -> ExtractedTextCreate:
    error = result.metadata.get("error")
    if error:
        raise RuntimeError(f"xberg extraction error: {error}")

    page_width = result.metadata.get("width")
    page_height = result.metadata.get("height")

    metadata = DocumentMetadata(
        filename=file_resource["filename"],
        title=result.metadata.get("title"),
        authors=result.metadata.get("authors") or [],
        keywords=result.metadata.get("keywords") or [],
        date_content_created=_parse_xberg_datetime(result.metadata.get("created_at")),
        date_content_modified=_parse_xberg_datetime(result.metadata.get("modified_at")),
        detected_language=result.get_detected_language(),
        page_count=result.get_page_count(),
        tables=[
            ExtractedTableInfo(
                cells=t.cells,
                markdown=t.markdown,
                page_number=t.page_number,
                bounding_box=_normalize_bbox(t.bounding_box, page_width, page_height),
            )
            for t in (result.tables or [])
        ]
        or None,
        document_structure=_document_structure_from_kreuzberg(result.document, page_width, page_height),
        sent_from=parent_email_metadata.sent_from if parent_email_metadata else None,
        sent_to=parent_email_metadata.sent_to if parent_email_metadata else [],
    )

    return ExtractedTextCreate(
        file_id=file_resource["id"],
        content=result.content,
        content_format=ExtractionContentFormat.MARKDOWN,
        extractor=TextExtractor.KREUZBERG,
        metadata=metadata,
        prechunked=_prechunked_from_kreuzberg(result.chunks) if use_chunking and result.chunks else None,
    )


async def queue_document_extraction_enrichments(session: "AsyncSession", dataset_id: str) -> int:
    """Queue TEXT_EXTRACTION enrichments for a dataset's document files."""
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    count = await enrichment_repo.queue_enrichments_by_filter(
        dataset_id=dataset_id,
        enrichment_type=EnrichmentType.TEXT_EXTRACTION,
        filetype_group="document",
    )
    await session.commit()
    return count


async def extract_documents_workflow(
    session: "AsyncSession",
    dataset_id: str,
    chunker: Chunker = Chunker.CLIR,
    tokenizer_model_dir: Path | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    batch_size: int = 50,
) -> int:
    """Extract text for a dataset's documents in xberg-batched passes. Returns files processed."""
    logger.debug(f"extract_documents_workflow starting for dataset {dataset_id} (chunker={chunker.value})")
    enrichment_repo = PostgresEnrichmentRepository(session=session)

    # Attachments only exist once extract_emails_workflow has parsed their
    # source email -- if emails are still pending/failed extraction, this run
    # may miss attachments that a later run would have picked up. Not fatal
    # (both workflows are idempotent and safe to re-run), just worth flagging.
    pending_emails = await enrichment_repo.get_pending_batch(
        enrichment_type=EnrichmentType.TEXT_EXTRACTION,
        enrichable_type=EnrichableType.FILE,
        batch_size=1,
        dataset_id=dataset_id,
        filetype_group_filter="email",
    )
    if pending_emails:
        logger.warning(
            "This dataset has emails not yet extracted -- running extract_documents_workflow now may miss "
            "attachments discovered by extract_emails_workflow. Consider running emails first (or again after)."
        )

    await queue_document_extraction_enrichments(session=session, dataset_id=dataset_id)

    extracted_text_repo = PostgresExtractedTextRepository(session=session)
    use_chunking = chunker == Chunker.KREUZBERG

    start = perf_counter()
    count = 0

    while True:
        batch = await enrichment_repo.get_pending_batch(
            enrichment_type=EnrichmentType.TEXT_EXTRACTION,
            enrichable_type=EnrichableType.FILE,
            batch_size=batch_size,
            dataset_id=dataset_id,
            filetype_group_filter="document",
        )
        if not batch:
            break

        logger.debug(f"Processing batch of {len(batch)} pending documents")
        await enrichment_repo.mark_processing(enrichment_ids=[item.enrichment.id for item in batch])
        await session.commit()

        # xberg's batch API needs local paths -- files without one (e.g. not
        # yet downloaded from a remote store) can't be batched and fail fast.
        resolvable = [item for item in batch if item.resource.get("path")]
        failed = [item.enrichment.id for item in batch if not item.resource.get("path")]
        completed = []

        if resolvable:
            paths = [item.resource["path"] for item in resolvable]
            logger.debug(f"Running xberg batch extraction over {len(paths)} files (chunking={use_chunking})")
            try:
                results = await anyio.to_thread.run_sync(
                    _run_batch, paths, use_chunking, tokenizer_model_dir, chunk_size
                )
            except Exception as e:
                logger.error(f"Batch extraction failed for {len(paths)} files: {e}")
                results = []

            for item, result in zip(resolvable, results, strict=False):
                try:
                    parent_email_metadata = None
                    if parent_id := item.resource.get("parent_id"):
                        parent_extracted = await extracted_text_repo.get_by_file_id(parent_id)
                        if parent_extracted and isinstance(parent_extracted.metadata, EmailMetadata):
                            parent_email_metadata = parent_extracted.metadata

                    extracted = _build_extracted_text(item.resource, result, use_chunking, parent_email_metadata)
                    await extracted_text_repo.upsert(extracted)
                    completed.append(item.enrichment.id)
                except Exception as e:
                    logger.error(f"Extraction failed for file {item.resource['id']}: {e}")
                    failed.append(item.enrichment.id)

            # Any resolvable items the batch call itself didn't return a result for
            failed.extend(item.enrichment.id for item in resolvable[len(results) :])

        if completed:
            await enrichment_repo.mark_completed_batch(completed)
        if failed:
            await enrichment_repo.mark_failed_batch(failed, increment_retry=True)
        await session.commit()

        count += len(completed)
        logger.info(f"Extracted {len(completed)} document files ({count} total)")

    total_ms = int((perf_counter() - start) * 1000)
    logger.success(f"Extracted text for {count} document files in {total_ms}ms")
    return count


async def get_extraction_stats(session: "AsyncSession", dataset_id: str | None = None) -> dict:
    """Get enrichment stats for text extraction (documents and emails share one enrichment type)."""
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    return await enrichment_repo.get_enrichment_stats(
        enrichable_type=EnrichableType.FILE,
        dataset_id=dataset_id,
        enrichment_type=EnrichmentType.TEXT_EXTRACTION,
    )
