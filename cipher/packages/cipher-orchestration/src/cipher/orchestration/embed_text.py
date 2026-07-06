"""Text embedding workflow (Stage 2) -- chunk + embed extracted text into the unified ES index.

Reads persisted `ExtractedText` rows (written by extract_emails.py /
extract_documents.py) rather than re-parsing files. When prechunked spans
already exist (chunker=kreuzberg was used at extraction time), those are
embedded directly -- no second split. Otherwise CLIR's `PlainTextChunker`
splits the extracted text now, using the same `chunk_size` as
extract_documents.py's xberg chunker so chunk boundaries don't drift
depending on which chunker produced them.
"""

from typing import TYPE_CHECKING, Any

import anyio
from loguru import logger
from tqdm import tqdm

from cipher.datastores.elasticsearch.repositories.text_chunk import ElasticsearchTextChunkRepository
from cipher.datastores.postgres.repositories import (
    PostgresEnrichmentRepository,
    PostgresExtractedTextRepository,
    PostgresFileRepository,
)
from cipher.orchestration.extract_documents import DEFAULT_CHUNK_SIZE
from cipher.schemas.document import DocumentMetadata, DocumentTextChunk
from cipher.schemas.email import EmailMetadata, EmailTextChunk
from cipher.schemas.enrichment import EnrichableType, EnrichmentType
from cipher.schemas.extraction import ExtractedText
from cipher.schemas.search import TextChunk

if TYPE_CHECKING:
    from clir.models.pytorch import TextEmbeddingPytorchModel
    from clir.utils.text_chunk import PlainTextChunker
    from sqlalchemy.ext.asyncio import AsyncSession

# Both document and email files land here once their respective extraction
# workflow (extract_emails.py / extract_documents.py) has completed.
_TEXT_GROUPS = ("document", "email")


def _split_if_oversized(span: dict, chunker: "PlainTextChunker") -> list[dict]:
    """Re-split a span that exceeds the token budget.

    xberg's own chunker (prechunked) can size by characters rather than
    tokens, and its markdown chunker treats some blocks (e.g. large tables)
    as atomic -- either way can hand back a span well over the embedding
    model's budget, which then OOMs the GPU on encode. CLIR's own chunk()
    output never exceeds the budget by construction, so this is a no-op for
    the non-prechunked path.
    """
    token_count = len(chunker.tokenizer(span["content"], add_special_tokens=False)["input_ids"])
    if token_count <= chunker.token_budget:
        return [span]
    base_offset = span["start_offset"]
    return [
        {
            "content": sub.content,
            "start_offset": base_offset + sub.start_offset,
            "end_offset": base_offset + sub.end_offset,
        }
        for sub in chunker.chunk(span["content"])
    ]


def _spans_for(extracted: ExtractedText, chunker: "PlainTextChunker") -> list[dict]:
    """Chunk boundaries either from xberg's own chunker (prechunked) or CLIR's now."""
    if not extracted.prechunked:
        return [
            {"content": s.content, "start_offset": s.start_offset, "end_offset": s.end_offset}
            for s in chunker.chunk(extracted.content)
        ]
    spans = [
        {"content": s.content, "start_offset": s.start_offset, "end_offset": s.end_offset}
        for s in extracted.prechunked
    ]
    return [sub for span in spans for sub in _split_if_oversized(span, chunker)]


def _build_chunk(extracted: ExtractedText, dataset_id: str, span: dict, chunk_index: int, embedding: list[float]) -> TextChunk:
    base = dict(
        dataset_id=dataset_id,
        file_id=extracted.file_id,
        chunk_index=chunk_index,
        start_offset=span["start_offset"],
        end_offset=span["end_offset"],
        text=span["content"],
        embedding=embedding,
    )
    if isinstance(extracted.metadata, DocumentMetadata):
        # tables/document_structure are the whole document's structure, already
        # persisted once on ExtractedText -- denormalizing them onto every chunk
        # would repeat that payload per chunk for no query benefit.
        metadata = extracted.metadata.model_dump(exclude={"tables", "document_structure"})
        return DocumentTextChunk(**base, **metadata)
    if isinstance(extracted.metadata, EmailMetadata):
        return EmailTextChunk(**base, **extracted.metadata.model_dump())
    raise ValueError(f"No document/email metadata to embed for file_id={extracted.file_id!r}")


def _run_chunk_and_encode(
    extracted: ExtractedText,
    dataset_id: str,
    chunker: "PlainTextChunker",
    model: "TextEmbeddingPytorchModel",
    embed_batch_size: int,
) -> "list[Any]":
    """CPU/GPU-bound worker: split (if needed) and embed one file's extracted text.

    Encodes in sub-batches of `embed_batch_size` spans rather than one
    `model.encode` call per file -- a heavily-chunked file (hundreds of
    spans) would otherwise pad every span into a single tensor in one
    forward pass, which is what was blowing out GPU memory even with each
    individual chunk well within budget.
    """
    spans = _spans_for(extracted, chunker)
    if not spans:
        return []
    embeddings = []
    for i in range(0, len(spans), embed_batch_size):
        batch = spans[i : i + embed_batch_size]
        embeddings.extend(model.encode([s["content"] for s in batch], task="retrieval", is_query=False))
    return [
        _build_chunk(extracted, dataset_id, span, i, emb.tolist())
        for i, (span, emb) in enumerate(zip(spans, embeddings, strict=True))
    ]


async def _find_embedded_duplicate(
    file_repo: PostgresFileRepository,
    es_repo: ElasticsearchTextChunkRepository,
    file_id: str,
    sha256: str,
) -> list[TextChunk] | None:
    """Find another file's already-embedded chunks sharing this content hash."""
    for duplicate_file in await file_repo.find_duplicates(sha256=sha256):
        if duplicate_file.id == file_id:
            continue
        chunks = await es_repo.list_by_file_id(duplicate_file.id)
        if chunks:
            return chunks
    return None


async def dedupe_pending_text_embeddings(
    session: "AsyncSession",
    es_repo: ElasticsearchTextChunkRepository,
    dataset_id: str | None = None,
    batch_size: int = 100,
) -> int:
    """Resolve pending text embeddings whose content has already been embedded elsewhere.

    Mirrors embed_images.py's image dedupe: for each pending file, look for
    another file (any dataset) with the same sha256 that's already indexed
    into `text_chunks`, and reuse its offsets/text/embeddings instead of
    re-running the GPU model -- the expensive step here -- rebuilding this
    file's own metadata (filename, sender, etc.) onto each copied chunk
    rather than the duplicate's.
    """
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    file_repo = PostgresFileRepository(session=session)
    extracted_text_repo = PostgresExtractedTextRepository(session=session)

    total = 0
    for group in _TEXT_GROUPS:
        while True:
            batch = await enrichment_repo.get_pending_batch(
                enrichment_type=EnrichmentType.TEXT_EMBEDDING,
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
                duplicate_chunks = await _find_embedded_duplicate(file_repo, es_repo, file_id, sha256)
                if duplicate_chunks is None:
                    continue

                extracted = await extracted_text_repo.get_by_file_id(file_id)
                if extracted is None:
                    continue

                new_chunks = [
                    _build_chunk(
                        extracted,
                        item.resource["dataset_id"],
                        {"content": chunk.text, "start_offset": chunk.start_offset, "end_offset": chunk.end_offset},
                        chunk.chunk_index,
                        chunk.embedding,
                    )
                    for chunk in sorted(duplicate_chunks, key=lambda c: c.chunk_index)
                ]
                await es_repo.delete_by_file_id(file_id)
                await es_repo.bulk_index(new_chunks, show_progress=False)
                resolved.append(item.enrichment.id)

            if resolved:
                await enrichment_repo.mark_completed_batch(resolved)
                total += len(resolved)
                logger.info(f"Deduped {len(resolved)} text embeddings from existing content ({group})")

            # Always commit, even with nothing resolved -- get_pending_batch's
            # FOR UPDATE SKIP LOCKED holds a lock on the whole batch until
            # commit/rollback (see embed_images.py's dedupe_pending_embeddings).
            await session.commit()

            if len(resolved) < len(batch):
                # Remaining pending items are genuinely new content; stop here
                # rather than re-fetching the same unresolved rows forever.
                break

    return total


async def queue_text_embedding_enrichments(session: "AsyncSession", dataset_id: str) -> int:
    """Queue TEXT_EMBEDDING enrichments for a dataset's document + email files."""
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    total = 0
    for group in _TEXT_GROUPS:
        total += await enrichment_repo.queue_enrichments_by_filter(
            dataset_id=dataset_id,
            enrichment_type=EnrichmentType.TEXT_EMBEDDING,
            filetype_group=group,
        )
    await session.commit()
    return total


async def embed_text_workflow(
    session: "AsyncSession",
    dataset_id: str,
    model: "TextEmbeddingPytorchModel",
    es_repo: ElasticsearchTextChunkRepository,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = 0,
    min_chunk_tokens: int = 0,
    batch_size: int = 20,
    embed_batch_size: int = 32,
) -> int:
    """Chunk (if needed) and embed a dataset's extracted text into the unified ES index.

    Returns the number of files embedded (not the number of chunks).
    """
    from clir.utils.text_chunk import PlainTextChunker

    enrichment_repo = PostgresEnrichmentRepository(session=session)

    # A file only has ExtractedText once extract_emails_workflow /
    # extract_documents_workflow has processed it -- if extraction is still
    # pending/failed for this dataset, embedding now will just skip those
    # files (get_by_file_id returns None, marked failed) rather than embed
    # incomplete content, but it's cheaper to flag it up front.
    pending_extraction = await enrichment_repo.get_pending_batch(
        enrichment_type=EnrichmentType.TEXT_EXTRACTION,
        enrichable_type=EnrichableType.FILE,
        batch_size=1,
        dataset_id=dataset_id,
    )
    if pending_extraction:
        logger.warning(
            "This dataset has files not yet text-extracted -- embedding now will skip them. "
            "Consider running extract-text first (or again after)."
        )

    await queue_text_embedding_enrichments(session=session, dataset_id=dataset_id)
    await dedupe_pending_text_embeddings(session=session, es_repo=es_repo, dataset_id=dataset_id)

    extracted_text_repo = PostgresExtractedTextRepository(session=session)
    chunker = PlainTextChunker(
        tokenizer=model.tokenizer, chunk_size=chunk_size, chunk_overlap=chunk_overlap, min_chunk_tokens=min_chunk_tokens
    )

    total = 0
    for group in _TEXT_GROUPS:
        total += await enrichment_repo.count_pending(
            enrichment_type=EnrichmentType.TEXT_EMBEDDING,
            enrichable_type=EnrichableType.FILE,
            dataset_id=dataset_id,
            filetype_group_filter=group,
        )
    count = failed_count = chunk_count = 0

    with tqdm(total=total, desc="Embedding text", unit="file") as pbar:
        for group in _TEXT_GROUPS:
            while True:
                batch = await enrichment_repo.get_pending_batch(
                    enrichment_type=EnrichmentType.TEXT_EMBEDDING,
                    enrichable_type=EnrichableType.FILE,
                    batch_size=batch_size,
                    dataset_id=dataset_id,
                    filetype_group_filter=group,
                )
                if not batch:
                    break

                await enrichment_repo.mark_processing(enrichment_ids=[item.enrichment.id for item in batch])
                await session.commit()

                completed, failed = [], []
                all_chunks: list[TextChunk] = []
                for item in batch:
                    try:
                        extracted = await extracted_text_repo.get_by_file_id(item.resource["id"])
                        if extracted is None:
                            raise ValueError("No extracted text yet for this file")

                        chunks = await anyio.to_thread.run_sync(
                            _run_chunk_and_encode, extracted, item.resource["dataset_id"], chunker, model, embed_batch_size
                        )
                        all_chunks.extend(chunks)
                        completed.append(item.enrichment.id)
                    except Exception as e:
                        logger.error(f"Embedding failed for file {item.resource['id']}: {e}")
                        failed.append(item.enrichment.id)

                if all_chunks:
                    # Re-embedding a file replaces its prior chunks rather than
                    # appending duplicates alongside them.
                    for file_id in {c.file_id for c in all_chunks}:
                        await es_repo.delete_by_file_id(file_id)
                    await es_repo.bulk_index(all_chunks, show_progress=False)

                if completed:
                    await enrichment_repo.mark_completed_batch(completed)
                if failed:
                    await enrichment_repo.mark_failed_batch(failed, increment_retry=True)
                await session.commit()

                count += len(completed)
                failed_count += len(failed)
                chunk_count += len(all_chunks)
                pbar.set_postfix(chunks=chunk_count, failed=failed_count)
                pbar.update(len(completed) + len(failed))

    logger.success(f"Embedded text for {count} files into {chunk_count} chunks ({failed_count} failed)")
    return count


async def get_text_embedding_stats(session: "AsyncSession", dataset_id: str | None = None) -> dict:
    """Get enrichment stats for text embedding."""
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    return await enrichment_repo.get_enrichment_stats(
        enrichable_type=EnrichableType.FILE,
        dataset_id=dataset_id,
        enrichment_type=EnrichmentType.TEXT_EMBEDDING,
    )
