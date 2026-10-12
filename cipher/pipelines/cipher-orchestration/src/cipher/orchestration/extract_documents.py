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

import re
import shutil
from collections.abc import Sequence
from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from tempfile import mkdtemp
from typing import TYPE_CHECKING

import anyio
from loguru import logger
from tqdm import tqdm

from cipher.datastores.postgres.repositories import (
    PostgresEnrichmentRepository,
    PostgresExtractedTextRepository,
    PostgresFileRepository,
)
from cipher.schemas._base.detection import BoundingBox
from cipher.schemas.content.document import DocumentMetadata, DocumentStructureNode, ExtractedTableInfo
from cipher.schemas.content.email import EmailMetadata
from cipher.schemas.content.extraction import (
    ExtractedText,
    ExtractedTextCreate,
    ExtractionContentFormat,
    PrechunkedSpan,
    TextExtractor,
)
from cipher.schemas.ingestion.enrichment import DEFAULT_FILETYPE_GROUPS, EnrichableType, EnrichmentType
from cipher.utils.io import suffixed_path
from cipher.utils.uri import MAX_IN_MEMORY_BYTES, is_local, local_copy, local_path, read_bytes

if TYPE_CHECKING:
    from kreuzberg import ExtractionResult
    from sqlalchemy.ext.asyncio import AsyncSession

# Shared with embed_text.py's CLIR chunker -- both take this as their
# `chunk_size` default so chunk boundaries don't drift depending on which
# chunker produced them for otherwise-similar documents.
DEFAULT_CHUNK_SIZE = 256
# xberg's per-page `is_blank` is exact (any text layer at all is "not blank"), so a scan
# carrying only a Bates stamp or page number would slip through; count it as image-based
# when its text layer has fewer word characters than this (matches pyvllm.ocr's rule).
IMAGE_PAGE_MIN_CHARS = 20
_WORD_CHAR_RE = re.compile(r"\w", re.UNICODE)


class Chunker(StrEnum):
    """Which chunker splits a document's extracted text into embeddable pieces.

    KREUZBERG produces chunks as part of the same xberg extraction call, not
    a separate pass. CLIR is the alternative, applied as a later stage
    (embed_text.py).
    """

    KREUZBERG = "kreuzberg"
    CLIR = "clir"


class OcrBackend(StrEnum):
    """OCR engine xberg runs over image-based PDF pages during `extract-text`."""

    EASYOCR = "easyocr"
    TESSERACT = "tesseract"
    NONE = "none"


@dataclass
class XbergOcr:
    """OCR settings for xberg's inline pass (a stronger model can re-run `image_pages` later via `ocr`).

    `languages` are the backend's own codes (EasyOCR `en`/`fr`..., Tesseract `eng`/`fra`...).
    `model_dir` points EasyOCR at pre-downloaded weights so it never reaches the network.
    """

    backend: OcrBackend = OcrBackend.EASYOCR
    languages: list[str] = field(default_factory=lambda: ["en"])
    model_dir: Path | None = None


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
        heading_path = [h["text"] for h in heading_context["headings"]] if heading_context else None
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


def _fallback_json_tables(file_resource: dict) -> list[ExtractedTableInfo]:
    """Table view for JSON/JSONL, which xberg extracts as text but not as a table.

    Reads the same file xberg already extracted from, rather than
    threading file bytes through the batch pipeline just for this.
    """
    from pyparse.parsers.tabular.json_tabular import flatten_json_records

    data = read_bytes(file_resource["uri"])
    cells = flatten_json_records(data, jsonl=file_resource["filetype"] == "jsonl")
    if not cells:
        return []
    return [ExtractedTableInfo(cells=cells, markdown=_cells_to_markdown(cells), page_number=1)]


def _cells_to_markdown(cells: list[list[str]]) -> str:
    header, *rows = cells
    lines = [f"| {' | '.join(header)} |", f"| {' | '.join(['---'] * len(header))} |"]
    lines.extend(f"| {' | '.join(row)} |" for row in rows)
    return "\n".join(lines) + "\n"


def _image_pages(result: "ExtractionResult") -> list[int]:
    """A PDF's image-based pages, from xberg's own no-OCR page output."""
    if result.mime_type != "application/pdf":
        return []
    return [
        page["page_number"]
        for page in result.pages or []
        if page.get("is_blank") or len(_WORD_CHAR_RE.findall(page["content"] or "")) < IMAGE_PAGE_MIN_CHARS
    ]


def _reader_suffix(file_resource: dict) -> str:
    """The extension xberg should see: the name's own (less a compression suffix once decoded), else the filetype's."""
    name = Path(file_resource["filename"])
    if file_resource.get("compression"):
        name = name.with_suffix("")
    return name.suffix.lower() or f".{file_resource['filetype']}"


_XBERG_ERROR = re.compile(r"^Error: \w+ error: ")


def _xberg_error(result: "ExtractionResult") -> str | None:
    """The failure message when xberg's batch API returned one in place of the file's text (never store it)."""
    if not result.metadata and _XBERG_ERROR.match(result.content or ""):
        return result.content[:500]
    return None


def _extract_batch(sources: "list[str | tuple[bytes, str]]", config, **kwargs) -> "list[ExtractionResult]":
    """Xberg's batch extraction over local paths and in-memory `(bytes, mime type)` alike, results in input order."""
    from kreuzberg import batch_extract_bytes_sync, batch_extract_files_sync

    file_configs = kwargs.pop("file_configs", None)
    results: list = [None] * len(sources)
    for wanted, run in ((str, batch_extract_files_sync), (tuple, batch_extract_bytes_sync)):
        picked = [i for i, source in enumerate(sources) if isinstance(source, wanted)]
        if not picked:
            continue
        configs = [file_configs[i] for i in picked] if file_configs else None
        if wanted is str:
            found = run([sources[i] for i in picked], config=config, file_configs=configs, **kwargs)
        else:
            data, mime_types = zip(*(sources[i] for i in picked), strict=True)
            found = run(list(data), list(mime_types), config=config, file_configs=configs, **kwargs)
        for i, result in zip(picked, found, strict=True):
            results[i] = result
    return results


def _run_batch(
    paths: "list[str | tuple[bytes, str]]",
    use_chunking: bool,
    tokenizer_model_dir: Path | None,
    chunk_size: int,
    max_concurrent_extractions: int | None = None,
    ocr: XbergOcr | None = None,
) -> "list[tuple[ExtractionResult, list[int]]]":
    """CPU-bound worker: xberg's batched extraction call, run off the event loop.

    Each source is a local path, or `(bytes, mime type)` for a file read from a remote uri.

    Returns each result with its PDF's image-based pages, read from xberg's own
    per-page output of a first, no-OCR pass. With `ocr` set, PDFs that have any are
    re-extracted OCRing just those pages (`force_ocr_pages`) -- xberg's automatic OCR
    decides per document, so on a mixed PDF it would re-read the text-layer pages too.

    xberg parallelizes internally (Rayon thread pool) across the batch --
    `max_concurrent_extractions` caps how many files it processes at once,
    defaulting to its own `num_cpus * 2` when left None. Python-level
    threading/multiprocessing around this call would just double up on
    parallelism xberg already provides; tune this instead, benchmarked via
    `cipher benchmark-ingest`, if extraction is CPU-underutilized or
    memory-constrained on a given machine.
    """
    from kreuzberg import (
        ChunkingConfig,
        ExtractionConfig,
        FileExtractionConfig,
        HierarchyConfig,
        OcrConfig,
        PageConfig,
        PdfConfig,
    )

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
    use_ocr = ocr is not None and ocr.backend != OcrBackend.NONE
    ocr_config = None
    easyocr_kwargs = None
    if use_ocr:
        is_easyocr = ocr.backend == OcrBackend.EASYOCR
        ocr_config = OcrConfig(
            backend=ocr.backend.value, language=ocr.languages[0] if is_easyocr else "+".join(ocr.languages)
        )
        if is_easyocr:
            easyocr_kwargs = {"languages": ocr.languages}
            if ocr.model_dir:
                easyocr_kwargs["model_storage_directory"] = str(ocr.model_dir)
    base = {
        "chunking": chunking,
        "include_document_structure": True,
        "pdf_options": PdfConfig(hierarchy=HierarchyConfig(include_bbox=True)),
        "max_concurrent_extractions": max_concurrent_extractions,
        # per-page output is what `_image_pages` reads, and xberg silently ignores
        # `force_ocr_pages` without it
        "pages": PageConfig(extract_pages=True),
    }
    results = _extract_batch(paths, ExtractionConfig(**base))
    image_pages = [_image_pages(result) for result in results]

    to_ocr = [i for i, pages in enumerate(image_pages) if pages] if use_ocr else []
    if to_ocr:
        ocr_results = _extract_batch(
            [paths[i] for i in to_ocr],
            ExtractionConfig(**base, ocr=ocr_config),
            file_configs=[FileExtractionConfig(force_ocr_pages=image_pages[i]) for i in to_ocr],
            easyocr_kwargs=easyocr_kwargs,
        )
        for i, result in zip(to_ocr, ocr_results, strict=True):
            results[i] = result
    return list(zip(results, image_pages, strict=False))


def _build_extracted_text(
    file_resource: dict,
    result: "ExtractionResult",
    use_chunking: bool,
    parent_email_metadata: EmailMetadata | None,
    image_pages: list[int] | None = None,
    ocr_backend: OcrBackend = OcrBackend.NONE,
) -> ExtractedTextCreate:
    error = result.metadata.get("error")
    if error:
        raise RuntimeError(f"xberg extraction error: {error}")

    page_width = result.metadata.get("width")
    page_height = result.metadata.get("height")

    tables = [
        ExtractedTableInfo(
            cells=t.cells,
            markdown=t.markdown,
            page_number=t.page_number,
            bounding_box=_normalize_bbox(t.bounding_box, page_width, page_height),
        )
        for t in (result.tables or [])
    ]
    if not tables and file_resource.get("filetype") in {"json", "jsonl"}:
        tables = _fallback_json_tables(file_resource)

    metadata = DocumentMetadata(
        filename=file_resource["filename"],
        title=result.metadata.get("title"),
        authors=result.metadata.get("authors") or [],
        keywords=result.metadata.get("keywords") or [],
        date_content_created=_parse_xberg_datetime(result.metadata.get("created_at")),
        date_content_modified=_parse_xberg_datetime(result.metadata.get("modified_at")),
        detected_language=result.get_detected_language(),
        page_count=result.get_page_count(),
        tables=tables or None,
        document_structure=_document_structure_from_kreuzberg(result.document, page_width, page_height),
        image_pages=image_pages or [],
        ocr_pages=image_pages if image_pages and ocr_backend != OcrBackend.NONE else [],
        ocr_model=ocr_backend.value if image_pages and ocr_backend != OcrBackend.NONE else None,
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


async def _find_extracted_duplicate(
    file_repo: PostgresFileRepository,
    extracted_text_repo: PostgresExtractedTextRepository,
    file_id: str,
    sha256: str,
) -> ExtractedText | None:
    """Find another file's already-extracted text sharing this content hash."""
    for duplicate_file in await file_repo.find_duplicates(sha256=sha256):
        if duplicate_file.id == file_id:
            continue
        extracted = await extracted_text_repo.get_by_file_id(duplicate_file.id)
        if extracted is not None:
            return extracted
    return None


async def dedupe_pending_extractions(
    session: "AsyncSession",
    dataset_id: str | None = None,
    batch_size: int = 100,
    group: str = "document",
) -> int:
    """Resolve pending document extractions whose content has already been extracted elsewhere.

    Cheap pre-pass mirroring embed_images.py's image dedupe: for each pending
    document, look for another file (any dataset) with the same sha256 that's
    already been through xberg, and copy its extracted content/structure
    instead of re-running OCR/parsing -- the expensive step in this pipeline.
    `filename` and email-attachment context (`sent_from`/`sent_to`) are
    re-derived for this file rather than copied, since a byte-identical
    attachment can arrive under a different name or from a different parent
    email.
    """
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    file_repo = PostgresFileRepository(session=session)
    extracted_text_repo = PostgresExtractedTextRepository(session=session)

    total = 0
    while True:
        batch = await enrichment_repo.get_pending_batch(
            enrichment_type=EnrichmentType.TEXT_EXTRACTION,
            enrichable_type=EnrichableType.FILE,
            batch_size=batch_size,
            dataset_id=dataset_id,
            filetype_group_filter=group,
        )
        if not batch:
            break

        resolved = []
        for item in batch:
            file_id, sha256 = item.resource["id"], item.resource["sha256"]
            duplicate = await _find_extracted_duplicate(
                file_repo=file_repo, extracted_text_repo=extracted_text_repo, file_id=file_id, sha256=sha256
            )
            if duplicate is None:
                continue

            metadata = duplicate.metadata
            if isinstance(metadata, DocumentMetadata):
                parent_email_metadata = None
                if parent_id := item.resource.get("parent_id"):
                    parent_extracted = await extracted_text_repo.get_by_file_id(parent_id)
                    if parent_extracted and isinstance(parent_extracted.metadata, EmailMetadata):
                        parent_email_metadata = parent_extracted.metadata
                metadata = metadata.model_copy(
                    update={
                        "filename": item.resource["filename"],
                        "sent_from": parent_email_metadata.sent_from if parent_email_metadata else None,
                        "sent_to": parent_email_metadata.sent_to if parent_email_metadata else [],
                    }
                )

            await extracted_text_repo.upsert(
                ExtractedTextCreate(
                    file_id=file_id,
                    content=duplicate.content,
                    content_format=duplicate.content_format,
                    extractor=duplicate.extractor,
                    metadata=metadata,
                    prechunked=duplicate.prechunked,
                    is_content_corrected=duplicate.is_content_corrected,
                    content_corrected_by=duplicate.content_corrected_by,
                    corrected_ranges=duplicate.corrected_ranges,
                )
            )
            resolved.append(item.enrichment.id)

        if resolved:
            await enrichment_repo.mark_completed_batch(resolved)
            total += len(resolved)
            logger.info(f"Deduped {len(resolved)} document extractions from existing content")

        # Always commit, even with nothing resolved -- get_pending_batch's FOR
        # UPDATE SKIP LOCKED holds a lock on the whole batch until commit/
        # rollback (see embed_images.py's dedupe_pending_embeddings).
        await session.commit()

        if len(resolved) < len(batch):
            # Remaining pending items are genuinely new content; stop here
            # rather than re-fetching the same unresolved rows forever.
            break

    return total


async def queue_document_extraction_enrichments(
    session: "AsyncSession", dataset_id: str, groups: tuple[str, ...] = ("document",)
) -> int:
    """Queue TEXT_EXTRACTION enrichments for a dataset's files in `groups` (documents; tables only when asked)."""
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    count = 0
    for group in groups:
        count += await enrichment_repo.queue_enrichments_by_filter(
            dataset_id=dataset_id,
            enrichment_type=EnrichmentType.TEXT_EXTRACTION,
            filetype_group=group,
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
    max_concurrent_extractions: int | None = None,
    ocr: XbergOcr | None = None,
    filetype_groups: Sequence[str] = DEFAULT_FILETYPE_GROUPS[EnrichmentType.TEXT_EXTRACTION],
) -> int:
    """Extract text for a dataset's files in `filetype_groups`, in xberg-batched passes. Returns files processed.

    Defaults to documents. Spreadsheets (`table`) are left out unless asked for: `cipher
    map-tables` maps them column by column. Included, their flattened text is stored like
    any document's, for embedding / NER runs that also list `table`.

    Every PDF's image-based pages are recorded (`metadata.image_pages`) whether or
    not `ocr` is set; with it, xberg OCRs just those pages inline.

    `max_concurrent_extractions` caps xberg's own internal parallelism per
    batch; left None, xberg defaults to `num_cpus * 2`. Tune this (and
    `batch_size`, which needs to be at least as large to keep xberg's pool
    fed) via `cipher benchmark-ingest`, not by adding Python-level
    threading/multiprocessing around this call -- see `_run_batch`.
    """
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

    groups = tuple(group for group in filetype_groups if group != "email")
    await queue_document_extraction_enrichments(session=session, dataset_id=dataset_id, groups=groups)
    for group in groups:
        await dedupe_pending_extractions(session=session, dataset_id=dataset_id, group=group)

    extracted_text_repo = PostgresExtractedTextRepository(session=session)
    use_chunking = chunker == Chunker.KREUZBERG

    total = 0
    for group in groups:
        total += await enrichment_repo.count_pending(
            enrichment_type=EnrichmentType.TEXT_EXTRACTION,
            enrichable_type=EnrichableType.FILE,
            dataset_id=dataset_id,
            filetype_group_filter=group,
        )
    count = failed_count = 0
    pending_groups = list(groups)

    with tqdm(total=total, desc="Extracting documents", unit=" file") as pbar:
        while pending_groups:
            batch = await enrichment_repo.get_pending_batch(
                enrichment_type=EnrichmentType.TEXT_EXTRACTION,
                enrichable_type=EnrichableType.FILE,
                batch_size=batch_size,
                dataset_id=dataset_id,
                filetype_group_filter=pending_groups[0],
            )
            if not batch:
                pending_groups.pop(0)
                continue

            await enrichment_repo.mark_processing(enrichment_ids=[item.enrichment.id for item in batch])
            await session.commit()

            # Local files go to xberg by path (a link carrying the extension when the name has
            # none); remote ones as bytes with their mime type, or a temp copy when too big for memory.
            resolvable, failed = [], {}
            completed = []
            links_dir = Path(mkdtemp(prefix="cipher-xberg-"))
            copies = ExitStack()
            xberg_paths: list[str | tuple[bytes, str]] = []
            for item in batch:
                uri, suffix = item.resource["uri"], _reader_suffix(item.resource)
                try:
                    if is_local(uri):
                        xberg_paths.append(str(suffixed_path(local_path(uri), suffix, links_dir)))
                    elif (item.resource.get("size") or 0) <= MAX_IN_MEMORY_BYTES and item.resource.get("mime_type"):
                        data = await anyio.to_thread.run_sync(read_bytes, uri)
                        xberg_paths.append((data, item.resource["mime_type"]))
                    else:
                        xberg_paths.append(str(copies.enter_context(local_copy(uri, suffix=suffix))))
                    resolvable.append(item)
                except (OSError, ValueError) as e:
                    failed[item.enrichment.id] = f"File could not be read: {type(e).__name__}: {e}"

            with copies:
                batch_error = "Batch extraction returned no result for this file"
                try:
                    results = await anyio.to_thread.run_sync(
                        _run_batch,
                        xberg_paths,
                        use_chunking,
                        tokenizer_model_dir,
                        chunk_size,
                        max_concurrent_extractions,
                        ocr,
                    )
                except Exception as e:
                    logger.error(f"Batch extraction failed for {len(xberg_paths)} files: {e}")
                    batch_error = f"Batch extraction failed: {type(e).__name__}: {e}"
                    results = []
                finally:
                    shutil.rmtree(links_dir, ignore_errors=True)

                for item, (result, image_pages) in zip(resolvable, results, strict=False):
                    if error := _xberg_error(result):
                        failed[item.enrichment.id] = error
                        continue
                    try:
                        parent_email_metadata = None
                        if parent_id := item.resource.get("parent_id"):
                            parent_extracted = await extracted_text_repo.get_by_file_id(parent_id)
                            if parent_extracted and isinstance(parent_extracted.metadata, EmailMetadata):
                                parent_email_metadata = parent_extracted.metadata

                        extracted = _build_extracted_text(
                            file_resource=item.resource,
                            result=result,
                            use_chunking=use_chunking,
                            parent_email_metadata=parent_email_metadata,
                            image_pages=image_pages,
                            ocr_backend=ocr.backend if ocr else OcrBackend.NONE,
                        )
                        await extracted_text_repo.upsert(extracted)
                        completed.append(item.enrichment.id)
                    except Exception as e:
                        logger.error(f"Extraction failed for file {item.resource['id']}: {e}")
                        await session.rollback()
                        failed[item.enrichment.id] = e

                # Any resolvable items the batch call itself didn't return a result for
                failed |= {item.enrichment.id: batch_error for item in resolvable[len(results) :]}

            if completed:
                await enrichment_repo.mark_completed_batch(completed)
            await enrichment_repo.mark_failed(failed)
            await session.commit()

            count += len(completed)
            failed_count += len(failed)
            pbar.set_postfix(failed=failed_count)
            pbar.update(len(completed) + len(failed))

    logger.success(f"Extracted text for {count} document files ({failed_count} failed)")
    return count


async def get_extraction_stats(session: "AsyncSession", dataset_id: str | None = None) -> dict:
    """Get enrichment stats for text extraction (documents and emails share one enrichment type)."""
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    return await enrichment_repo.get_enrichment_stats(
        enrichable_type=EnrichableType.FILE,
        dataset_id=dataset_id,
        enrichment_type=EnrichmentType.TEXT_EXTRACTION,
    )
