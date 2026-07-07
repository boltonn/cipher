"""Text embedding workflow (Stage 2) -- chunk + embed extracted text into the unified ES index.

Reads persisted `ExtractedText` rows (written by extract_emails.py /
extract_documents.py) rather than re-parsing files. When prechunked spans
already exist (chunker=kreuzberg was used at extraction time), those are
embedded directly -- no second split. Otherwise CLIR's `PlainTextChunker`
splits the extracted text now, using the same `chunk_size` as
extract_documents.py's xberg chunker so chunk boundaries don't drift
depending on which chunker produced them.

Chunking (CPU) and embedding (GPU) run as a producer/consumer pipeline
(mirrors embed_images.py) rather than one file at a time end-to-end -- doing
both stages inline per file serializes CPU tokenization and GPU inference,
leaving the GPU idle while the next file tokenizes. The producer tokenizes
files in a thread pool and feeds the consumer fixed-size span batches
regardless of which file they came from, so a heavily-chunked file doesn't
stall the GPU queue and a one-chunk email doesn't underfill a batch.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
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
from cipher.schemas.enrichment import EnrichableType, EnrichmentBatchItem, EnrichmentType
from cipher.schemas.extraction import ExtractedText
from cipher.schemas.search import TextChunk

if TYPE_CHECKING:
    from clir.models.pytorch import TextEmbeddingPytorchModel
    from clir.utils.text_chunk import PlainTextChunker

# Both document and email files land here once their respective extraction
# workflow (extract_emails.py / extract_documents.py) has completed.
_TEXT_GROUPS = ("document", "email")

# Tokenizing (CPU) is what the producer offloads here -- HF's fast (Rust)
# tokenizers release the GIL during encode, so threads (not processes) give
# real parallelism without the IPC cost of shipping large text blobs around.
_EXECUTOR = ThreadPoolExecutor(max_workers=4)


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
        {"content": s.content, "start_offset": s.start_offset, "end_offset": s.end_offset} for s in extracted.prechunked
    ]
    return [sub for span in spans for sub in _split_if_oversized(span, chunker)]


def _build_chunk(
    extracted: ExtractedText,
    dataset_id: str,
    filetype: str,
    span: dict,
    chunk_index: int,
    embedding: list[float],
) -> TextChunk:
    base = dict(
        dataset_id=dataset_id,
        file_id=extracted.file_id,
        filetype=filetype,
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
                duplicate_chunks = await _find_embedded_duplicate(
                    file_repo=file_repo, es_repo=es_repo, file_id=file_id, sha256=sha256
                )
                if duplicate_chunks is None:
                    continue

                extracted = await extracted_text_repo.get_by_file_id(file_id)
                if extracted is None:
                    continue

                new_chunks = [
                    _build_chunk(
                        extracted=extracted,
                        dataset_id=item.resource["dataset_id"],
                        filetype=item.resource["filetype"],
                        span={
                            "content": chunk.text,
                            "start_offset": chunk.start_offset,
                            "end_offset": chunk.end_offset,
                        },
                        chunk_index=chunk.chunk_index,
                        embedding=chunk.embedding,
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


@dataclass
class _PendingFile:
    """Tracks one file's spans as they trickle back embedded, possibly out of batch order."""

    item: EnrichmentBatchItem
    extracted: ExtractedText
    total: int
    seen: int = 0
    failed: bool = False
    chunks: list[TextChunk] = field(default_factory=list)


async def _producer(
    queue: "asyncio.Queue",
    session: "AsyncSession",
    chunker: "PlainTextChunker",
    dataset_id: str,
    group: str,
    batch_size: int,
    embed_batch_size: int,
    stats: dict,
    pbar: tqdm,
) -> None:
    """Producer: pull pending files, tokenize/chunk them (CPU), and feed batches.

    Feeds the consumer fixed-size span batches regardless of which file each
    span came from, so the GPU always gets a full batch even when file chunk
    counts vary wildly (a one-chunk email next to a thousand-chunk document).
    """
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    extracted_text_repo = PostgresExtractedTextRepository(session=session)
    loop = asyncio.get_event_loop()

    pending_spans: list[tuple[_PendingFile, dict, int]] = []

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

        for item in batch:
            extracted = await extracted_text_repo.get_by_file_id(item.resource["id"])
            if extracted is None:
                logger.error(f"No extracted text yet for file {item.resource['id']}")
                await enrichment_repo.mark_failed_batch([item.enrichment.id], increment_retry=True)
                await session.commit()
                stats["failed"] += 1
                pbar.update(1)
                continue

            try:
                spans = await loop.run_in_executor(_EXECUTOR, _spans_for, extracted, chunker)
            except Exception as e:
                logger.error(f"Chunking failed for file {item.resource['id']}: {e}")
                await enrichment_repo.mark_failed_batch([item.enrichment.id], increment_retry=True)
                await session.commit()
                stats["failed"] += 1
                pbar.update(1)
                continue

            if not spans:
                await enrichment_repo.mark_completed_batch([item.enrichment.id])
                await session.commit()
                stats["files"] += 1
                pbar.update(1)
                continue

            file_ctx = _PendingFile(item=item, extracted=extracted, total=len(spans))
            for i, span in enumerate(spans):
                pending_spans.append((file_ctx, span, i))
                if len(pending_spans) >= embed_batch_size:
                    await queue.put(pending_spans)
                    pending_spans = []

    if pending_spans:
        await queue.put(pending_spans)
    await queue.put(None)


async def _consumer(
    queue: "asyncio.Queue",
    session: "AsyncSession",
    model: "TextEmbeddingPytorchModel",
    es_repo: ElasticsearchTextChunkRepository,
    commit_batch_size: int,
    stats: dict,
    pbar: tqdm,
) -> None:
    """Consumer: run GPU inference on span batches and persist completed files."""
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    ready: list[_PendingFile] = []
    failed: list[_PendingFile] = []

    async def _flush() -> None:
        if not ready and not failed:
            return
        chunks = [c for f in ready for c in f.chunks]
        for f in ready:
            await es_repo.delete_by_file_id(f.item.resource["id"])
        if chunks:
            await es_repo.bulk_index(chunks, show_progress=False)
        if ready:
            await enrichment_repo.mark_completed_batch([f.item.enrichment.id for f in ready])
        if failed:
            await enrichment_repo.mark_failed_batch([f.item.enrichment.id for f in failed], increment_retry=True)
        await session.commit()

        stats["files"] += len(ready)
        stats["failed"] += len(failed)
        stats["chunks"] += len(chunks)
        pbar.set_postfix(chunks=stats["chunks"], failed=stats["failed"])
        pbar.update(len(ready) + len(failed))
        ready.clear()
        failed.clear()

    while True:
        work = await queue.get()
        if work is None:
            queue.task_done()
            break

        contents = [span["content"] for _, span, _ in work]
        embeddings = await asyncio.to_thread(model.encode, contents, task="retrieval", is_query=False)

        for (file_ctx, span, idx), emb in zip(work, embeddings, strict=True):
            if file_ctx.failed:
                continue
            try:
                chunk = _build_chunk(
                    extracted=file_ctx.extracted,
                    dataset_id=file_ctx.item.resource["dataset_id"],
                    filetype=file_ctx.item.resource["filetype"],
                    span=span,
                    chunk_index=idx,
                    embedding=emb.tolist(),
                )
                file_ctx.chunks.append(chunk)
            except Exception as e:
                logger.error(f"Embedding failed for file {file_ctx.item.resource['id']}: {e}")
                file_ctx.failed = True

            file_ctx.seen += 1
            if file_ctx.seen == file_ctx.total:
                (failed if file_ctx.failed else ready).append(file_ctx)

        if len(ready) + len(failed) >= commit_batch_size:
            await _flush()

        queue.task_done()

    await _flush()


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
    commit_batch_size: int = 20,
) -> int:
    """Chunk (if needed) and embed a dataset's extracted text into the unified ES index.

    Runs documents and emails as separate producer/consumer pipelines (each
    with its own progress bar) so CPU tokenization and GPU embedding overlap
    within a group instead of serializing per file.

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

    chunker = PlainTextChunker(
        tokenizer=model.tokenizer, chunk_size=chunk_size, chunk_overlap=chunk_overlap, min_chunk_tokens=min_chunk_tokens
    )

    engine = session.bind
    total_count = total_failed = total_chunks = 0

    for group in _TEXT_GROUPS:
        pending = await enrichment_repo.count_pending(
            enrichment_type=EnrichmentType.TEXT_EMBEDDING,
            enrichable_type=EnrichableType.FILE,
            dataset_id=dataset_id,
            filetype_group_filter=group,
        )
        if not pending:
            continue

        stats = {"files": 0, "failed": 0, "chunks": 0}
        queue: asyncio.Queue = asyncio.Queue(maxsize=4)

        # _producer and _consumer run concurrently via gather, so each needs
        # its own AsyncSession -- a single session isn't safe for concurrent
        # use and will corrupt its transaction state under interleaved
        # commits/queries (see embed_images.py).
        with tqdm(total=pending, desc=f"Embedding {group}s", unit=" file") as pbar:
            async with AsyncSession(engine, expire_on_commit=False) as producer_session:
                async with AsyncSession(engine, expire_on_commit=False) as consumer_session:
                    await asyncio.gather(
                        _producer(
                            queue=queue,
                            session=producer_session,
                            chunker=chunker,
                            dataset_id=dataset_id,
                            group=group,
                            batch_size=batch_size,
                            embed_batch_size=embed_batch_size,
                            stats=stats,
                            pbar=pbar,
                        ),
                        _consumer(
                            queue=queue,
                            session=consumer_session,
                            model=model,
                            es_repo=es_repo,
                            commit_batch_size=commit_batch_size,
                            stats=stats,
                            pbar=pbar,
                        ),
                    )

        logger.success(f"Embedded {stats['files']} {group}s into {stats['chunks']} chunks ({stats['failed']} failed)")
        total_count += stats["files"]
        total_failed += stats["failed"]
        total_chunks += stats["chunks"]

    logger.success(f"Embedded text for {total_count} files into {total_chunks} chunks ({total_failed} failed)")
    return total_count


async def get_text_embedding_stats(session: "AsyncSession", dataset_id: str | None = None) -> dict:
    """Get enrichment stats for text embedding."""
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    return await enrichment_repo.get_enrichment_stats(
        enrichable_type=EnrichableType.FILE,
        dataset_id=dataset_id,
        enrichment_type=EnrichmentType.TEXT_EMBEDDING,
    )
