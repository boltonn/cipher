"""OCR workflow: image-based PDF pages and images -> `ExtractedText`, via the pyocr service.

Runs after `extract-text`. PDFs keep their xberg extraction for pages with a real
text layer; only pages pdfium finds (near) empty go to the model, and the result
is merged page-by-page into the same `ExtractedText` row (`metadata.ocr_pages`
records which pages are OCR'd). Images get a new row. Either way `prechunked`
carries one span per page so chunks keep real page numbers.

Speed: files are kept in a rolling in-flight window (not batch-and-wait), and the
service decodes every page of every in-flight file concurrently, so the GPU stays
saturated. Optionally, images are pre-filtered by zero-shot CLIP tags scored against
the embeddings `embed-images` already stored -- no image is re-read to decide.
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from loguru import logger
from pyocr.capabilities import IMAGE_FILETYPES, PDF_FILETYPES, SUPPORTED_FILETYPES
from pyocr.pages import DEFAULT_MIN_CHARS, scanned_pages
from pyocr.schemas import OcrRequest, OcrResponse
from tqdm import tqdm

from cipher.datastores.postgres.repositories import (
    PostgresEnrichmentRepository,
    PostgresExtractedTextRepository,
    PostgresFileRepository,
    PostgresImageRepository,
)
from cipher.orchestration.extract_documents import _find_extracted_duplicate
from cipher.schemas.content.document import DocumentMetadata, DocumentStructureNode
from cipher.schemas.content.extraction import (
    ExtractedText,
    ExtractedTextCreate,
    ExtractionContentFormat,
    PrechunkedSpan,
    TextExtractor,
)
from cipher.schemas.ingestion.enrichment import EnrichableType, EnrichmentType

if TYPE_CHECKING:
    from pyocr.client import OcrClient
    from setfitcv.model import CLIP
    from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_CLIP_TAGS = (
    "a screenshot",
    "a scanned document",
    "a photo of a document",
    "a receipt",
    "a handwritten note",
    "a sign with text",
    "a presentation slide",
    "a chart or diagram",
    "a map",
)
DEFAULT_CLIP_NEGATIVE_TAGS = (
    "a photo of a person",
    "a photo of a group of people",
    "a landscape photo",
    "a photo of an animal",
    "a photo of food",
    "a photo of a building",
    "a photo of an object",
)
# Enrichments that read `ExtractedText.content` and append rows (not idempotent per file).
_TEXT_CONSUMERS = (
    EnrichmentType.SELECTOR_EXTRACTION,
    EnrichmentType.ENTITY_EXTRACTION,
    EnrichmentType.EVENT_EXTRACTION,
    EnrichmentType.RELATIONSHIP_EXTRACTION,
)


@dataclass
class ClipTagFilter:
    """Zero-shot CLIP gate: keep an image when its probability mass on `tags` clears `threshold`."""

    tag_embeddings: np.ndarray
    positive_count: int
    threshold: float

    @classmethod
    def from_model(
        cls, model: "CLIP", tags: list[str], negative_tags: list[str], threshold: float = 0.5
    ) -> "ClipTagFilter":
        """Embed the tag prompts once with the CLIP text tower."""
        input_ids = model.preprocess_txt([*tags, *negative_tags])["input_ids"]
        return cls(
            tag_embeddings=np.asarray(model.embed_txt_batch(input_ids), dtype=np.float32),
            positive_count=len(tags),
            threshold=threshold,
        )

    def keep(self, embedding: list[float]) -> bool:
        """Softmax over all tags (CLIP logit scale 100); keep on enough mass on the text-bearing ones."""
        vector = np.asarray(embedding, dtype=np.float32)
        logits = 100.0 * self.tag_embeddings @ (vector / np.linalg.norm(vector))
        probabilities = np.exp(logits - logits.max())
        probabilities /= probabilities.sum()
        return float(probabilities[: self.positive_count].sum()) >= self.threshold


async def queue_ocr_enrichments(
    session: "AsyncSession",
    dataset_id: str,
    filetypes: list[str] | None = None,
    clip_filter: ClipTagFilter | None = None,
) -> int:
    """Queue OCR for eligible files; filetypes default to every PDF + supported image type.

    PDFs wait for `extract-text` (their OCR merges into that row, and a later
    extract-text would otherwise overwrite it). With `clip_filter`, only images whose
    stored CLIP embedding matches the tags are queued -- the rest stay unqueued, so a
    later unfiltered run still reaches them.
    """
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    extracted_text_repo = PostgresExtractedTextRepository(session=session)
    wanted = sorted(SUPPORTED_FILETYPES & set(filetypes)) if filetypes else sorted(SUPPORTED_FILETYPES)
    candidates = await enrichment_repo.get_unqueued_files(
        dataset_id=dataset_id, enrichment_type=EnrichmentType.OCR, filetypes=wanted
    )

    pdf_ids = [c["id"] for c in candidates if c["filetype"] in PDF_FILETYPES]
    ready_pdf_ids = await extracted_text_repo.get_file_ids_with_text(pdf_ids)
    if waiting := len(pdf_ids) - len(ready_pdf_ids):
        logger.warning(f"{waiting} PDFs have no extracted text yet -- run `extract-text` first; skipping them")

    images = [c for c in candidates if c["filetype"] in IMAGE_FILETYPES]
    if clip_filter and images:
        embeddings = await PostgresImageRepository(session=session).get_embeddings(list({c["sha256"] for c in images}))
        if unembedded := sum(c["sha256"] not in embeddings for c in images):
            logger.warning(f"{unembedded} images have no CLIP embedding -- run `embed-images` first; skipping them")
        kept = [c for c in images if c["sha256"] in embeddings and clip_filter.keep(embeddings[c["sha256"]])]
        logger.info(f"CLIP tag filter kept {len(kept)} of {len(images)} images")
        images = kept

    count = await enrichment_repo.queue_enrichments_for_files(
        file_ids=[*ready_pdf_ids, *(c["id"] for c in images)], enrichment_type=EnrichmentType.OCR
    )
    await session.commit()
    logger.info(f"Queued {count} ocr enrichments")
    return count


def _page_spans(page_texts: list[tuple[int, str]]) -> tuple[str, list[PrechunkedSpan]]:
    """Join pages with blank lines, one prechunked span per non-empty page (char offsets)."""
    parts, spans, offset = [], [], 0
    for number, text in page_texts:
        text = text.strip()
        if not text:
            continue
        if parts:
            offset += 2
        spans.append(
            PrechunkedSpan(
                content=text, start_offset=offset, end_offset=offset + len(text), first_page=number, last_page=number
            )
        )
        parts.append(text)
        offset += len(text)
    return "\n\n".join(parts), spans


def _native_page_texts(path: Path) -> dict[int, str]:
    """Per-page text from xberg itself, for the pages of a mixed PDF that weren't OCR'd."""
    from kreuzberg import ExtractionConfig, PageConfig, extract_file_sync

    result = extract_file_sync(
        str(path), config=ExtractionConfig(disable_ocr=True, pages=PageConfig(extract_pages=True))
    )
    return {page["page_number"]: page["content"] or "" for page in result.pages or []}


def build_ocr_extracted_text(
    file_resource: dict,
    response: OcrResponse,
    existing: ExtractedText | None,
    native_pages: dict[int, str],
) -> ExtractedTextCreate | None:
    """Merge OCR'd pages over the existing extraction (or start one). None when there's no text at all."""
    ocr_pages = {page.page_number: page for page in response.pages}
    page_texts = [
        (number, ocr_pages[number].markdown if number in ocr_pages else native_pages.get(number, ""))
        for number in range(1, response.page_count + 1)
    ]
    content, spans = _page_spans(page_texts)
    if not content and existing is None:
        return None

    base = existing.metadata if existing and isinstance(existing.metadata, DocumentMetadata) else None
    base = base or DocumentMetadata(filename=file_resource["filename"])
    figures = [
        DocumentStructureNode(
            id=f"ocr-p{page.page_number}-figure-{index}",
            node_type="figure",
            text=region.text,
            page=page.page_number,
            bounding_box=region.bounding_box,
        )
        for page in response.pages
        for index, region in enumerate(page.regions)
    ]
    tables = [
        *(t for t in base.tables or [] if t.page_number not in ocr_pages),
        *(t for page in response.pages for t in page.tables),
    ]
    nodes = [*(n for n in base.document_structure or [] if n.page not in ocr_pages), *figures]
    metadata = base.model_copy(
        update={
            "page_count": response.page_count,
            "ocr_pages": sorted(ocr_pages),
            "ocr_model": response.model,
            "tables": tables or None,
            "document_structure": nodes or None,
        }
    )
    return ExtractedTextCreate(
        file_id=file_resource["id"],
        content=content,
        content_format=ExtractionContentFormat.MARKDOWN,
        extractor=TextExtractor.PYOCR,
        metadata=metadata,
        prechunked=spans or None,
    )


async def _ocr_file(
    client: "OcrClient", file_resource: dict, min_chars: int, force: bool, figures: bool
) -> tuple[OcrResponse, dict[int, str]] | None:
    """Network + CPU only (no DB): pick pages, call the service, fetch native text for mixed PDFs."""
    path = Path(file_resource["path"])
    pages = None
    if file_resource["filetype"] in PDF_FILETYPES and not force:
        pages = await asyncio.to_thread(scanned_pages, path, min_chars)
        if not pages:
            return None
    response = await client.ocr(path, OcrRequest(pages=pages, figures=figures))
    native = {}
    if file_resource["filetype"] in PDF_FILETYPES and len(response.pages) < response.page_count:
        native = await asyncio.to_thread(_native_page_texts, path)
    return response, native


def _has_text(extracted: ExtractedText | None) -> bool:
    return extracted is not None and any(ch.isalnum() for ch in extracted.content)


def _copy_for(
    source: ExtractedText | ExtractedTextCreate, file_resource: dict, existing: ExtractedText | None
) -> ExtractedTextCreate:
    """A content-identical file's OCR result, re-labelled with this file's own name/email context."""
    own = existing.metadata if existing and isinstance(existing.metadata, DocumentMetadata) else None
    return ExtractedTextCreate(
        file_id=file_resource["id"],
        content=source.content,
        content_format=source.content_format,
        extractor=source.extractor,
        prechunked=source.prechunked,
        metadata=source.metadata.model_copy(
            update={
                "filename": file_resource["filename"],
                "sent_from": own.sent_from if own else None,
                "sent_to": own.sent_to if own else [],
            }
        ),
    )


async def _write(session: "AsyncSession", extracted: ExtractedTextCreate, existing: ExtractedText | None) -> bool:
    """Persist OCR text and requeue what reads it. True when older mentions may now be stale.

    Text always gets re-embedded. Mention-producing consumers are only re-run when the
    file had no text before -- they append rows, so re-running over replaced text
    would duplicate mentions; those files are reported instead.
    """
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    await PostgresExtractedTextRepository(session=session).upsert(extracted)
    file_ids = [extracted.file_id]
    await enrichment_repo.requeue(file_ids=file_ids, enrichment_type=EnrichmentType.TEXT_EMBEDDING, create_missing=True)
    if not _has_text(existing):
        for enrichment_type in _TEXT_CONSUMERS:
            await enrichment_repo.requeue(file_ids=file_ids, enrichment_type=enrichment_type)
        return False
    for enrichment_type in _TEXT_CONSUMERS:
        if await enrichment_repo.get_enrichment_ids_for(enrichable_ids=file_ids, enrichment_type=enrichment_type):
            return True
    return False


async def dedupe_pending_ocr(session: "AsyncSession", dataset_id: str) -> tuple[int, int]:
    """Copy OCR text from a content-identical file (any dataset) instead of re-running the model.

    Returns `(files deduped, files whose older mentions may now be stale)`.
    """
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    file_repo = PostgresFileRepository(session=session)
    extracted_text_repo = PostgresExtractedTextRepository(session=session)

    batch = await enrichment_repo.get_pending_batch(
        enrichment_type=EnrichmentType.OCR,
        enrichable_type=EnrichableType.FILE,
        batch_size=10_000,
        dataset_id=dataset_id,
    )
    resolved, stale = [], 0
    for item in batch:
        duplicate = await _find_extracted_duplicate(
            file_repo=file_repo,
            extracted_text_repo=extracted_text_repo,
            file_id=item.resource["id"],
            sha256=item.resource["sha256"],
        )
        if (
            duplicate is None
            or not isinstance(duplicate.metadata, DocumentMetadata)
            or not duplicate.metadata.ocr_model
        ):
            continue
        existing = await extracted_text_repo.get_by_file_id(item.resource["id"])
        stale += await _write(session, _copy_for(duplicate, item.resource, existing), existing)
        resolved.append(item.enrichment.id)
    if resolved:
        await enrichment_repo.mark_completed_batch(resolved)
        logger.info(f"Deduped {len(resolved)} OCR files from existing content")
    await session.commit()
    return len(resolved), stale


async def ocr_workflow(
    session: "AsyncSession",
    client: "OcrClient",
    dataset_id: str,
    filetypes: list[str] | None = None,
    clip_filter: ClipTagFilter | None = None,
    concurrency: int = 16,
    min_chars: int = DEFAULT_MIN_CHARS,
    force: bool = False,
    figures: bool = False,
) -> int:
    """Queue, dedupe, then OCR a dataset's eligible files. Returns files whose text was written.

    Files sharing a sha256 within the run are sent to the model once: later twins wait
    for the first and copy its result.
    """
    if not await client.health():
        raise RuntimeError("pyocr service is not reachable -- start it with `make start-vllm` in analytics/pyocr")
    await queue_ocr_enrichments(session=session, dataset_id=dataset_id, filetypes=filetypes, clip_filter=clip_filter)
    deduped, stale = await dedupe_pending_ocr(session=session, dataset_id=dataset_id)

    enrichment_repo = PostgresEnrichmentRepository(session=session)
    extracted_text_repo = PostgresExtractedTextRepository(session=session)
    total = await enrichment_repo.count_pending(
        enrichment_type=EnrichmentType.OCR, enrichable_type=EnrichableType.FILE, dataset_id=dataset_id
    )

    in_flight: dict[asyncio.Task, tuple] = {}
    twins: dict[str, list[tuple]] = {}
    exhausted = False
    written = skipped = failed = pages = 0

    def spawn(item, existing) -> None:
        task = asyncio.create_task(_ocr_file(client, item.resource, min_chars, force, figures))
        in_flight[task] = (item, existing)

    async def complete(item, extracted: ExtractedTextCreate | None, existing) -> None:
        nonlocal written, skipped, stale
        if extracted is None:
            skipped += 1
        else:
            stale += await _write(session, extracted, existing)
            written += 1
        await enrichment_repo.mark_completed_batch([item.enrichment.id])
        await session.commit()
        pbar.update(1)

    with tqdm(total=total, desc="OCR", unit=" file") as pbar:
        while True:
            # Top the window back up before waiting, so the service never idles between batches.
            while not exhausted and len(in_flight) < concurrency:
                batch = await enrichment_repo.get_pending_batch(
                    enrichment_type=EnrichmentType.OCR,
                    enrichable_type=EnrichableType.FILE,
                    batch_size=concurrency - len(in_flight),
                    dataset_id=dataset_id,
                )
                if not batch:
                    exhausted = True
                    break
                await enrichment_repo.mark_processing(enrichment_ids=[item.enrichment.id for item in batch])
                await session.commit()
                active = {entry[0].resource["sha256"] for entry in in_flight.values()}
                for item in batch:
                    existing = await extracted_text_repo.get_by_file_id(item.resource["id"])
                    if item.resource["sha256"] in active:
                        twins.setdefault(item.resource["sha256"], []).append((item, existing))
                    else:
                        active.add(item.resource["sha256"])
                        spawn(item, existing)
            if not in_flight:
                break

            done, _ = await asyncio.wait(in_flight, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                item, existing = in_flight.pop(task)
                waiting = twins.pop(item.resource["sha256"], [])
                try:
                    result = task.result()
                    extracted = None
                    if result is not None:
                        response, native = result
                        pages += len(response.pages)
                        extracted = build_ocr_extracted_text(item.resource, response, existing, native)
                    await complete(item, extracted, existing)
                    for twin, twin_existing in waiting:
                        copied = _copy_for(extracted, twin.resource, twin_existing) if extracted else None
                        await complete(twin, copied, twin_existing)
                except Exception as e:
                    logger.error(f"OCR failed for file {item.resource['id']}: {e}")
                    await session.rollback()
                    await enrichment_repo.mark_failed_batch(
                        [item.enrichment.id], error_message=str(e)[:2000], increment_retry=True
                    )
                    await session.commit()
                    failed += 1
                    pbar.update(1)
                    if waiting:
                        spawn(*waiting[0])
                        if waiting[1:]:
                            twins[item.resource["sha256"]] = waiting[1:]
                pbar.set_postfix(pages=pages, failed=failed)

    if stale:
        logger.warning(
            f"{stale} files already had text and extracted mentions before OCR; those mentions still reflect "
            "the old text -- `reset-entities` + re-run to re-extract them"
        )
    logger.success(
        f"OCR wrote text for {written} files ({pages} pages), {deduped} deduped, "
        f"{skipped} with nothing to OCR, {failed} failed"
    )
    return written + deduped


async def get_ocr_stats(session: "AsyncSession", dataset_id: str | None = None) -> dict:
    """OCR enrichment counts by status."""
    return await PostgresEnrichmentRepository(session=session).get_enrichment_stats(
        enrichable_type=EnrichableType.FILE, dataset_id=dataset_id, enrichment_type=EnrichmentType.OCR
    )
