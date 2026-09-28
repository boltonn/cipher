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
import re
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
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
from cipher.schemas.content.document import DocumentMetadata, DocumentTextChunk
from cipher.schemas.content.email import EmailMetadata, EmailState, EmailTextChunk
from cipher.schemas.content.extraction import ExtractedText
from cipher.schemas.content.search import TextChunk
from cipher.schemas.ingestion.enrichment import EnrichableType, EnrichmentBatchItem, EnrichmentType
from cipher.utils.retrieval import RetrievalBackend, load_retrieval_config

if TYPE_CHECKING:
    from clir.models.pytorch import TextEmbeddingPytorchModel
    from clir.utils.text_chunk import PlainTextChunker

# Both document and email files land here once their respective extraction
# workflow (extract_emails.py / extract_documents.py) has completed.
_TEXT_GROUPS = ("document", "email")
# OCR'd images carry text too, but only `ocr` queues them (most images have none).
_EMBED_GROUPS = (*_TEXT_GROUPS, "image")

# Tokenizing (CPU) is what the producer offloads here -- HF's fast (Rust)
# tokenizers release the GIL during encode, so threads (not processes) give
# real parallelism without the IPC cost of shipping large text blobs around.
_EXECUTOR = ThreadPoolExecutor(max_workers=4)

# Spam contributes noise chunks to the search index without triage value --
# skipped by default, overridable per run (embed-text --skip-email-state).
DEFAULT_SKIP_EMAIL_STATES = frozenset({EmailState.SPAM})


def _skip_email_state(extracted: ExtractedText, skip_email_states: frozenset[EmailState]) -> bool:
    return isinstance(extracted.metadata, EmailMetadata) and extracted.metadata.state in skip_email_states


def _truncate_to_pages(extracted: ExtractedText, max_pages: int | None) -> str:
    """Approximate a page cap for content with no per-span page info.

    CLIR-chunked documents only know their total `page_count`, not where page
    boundaries fall in the extracted text, so the cap is applied as a
    proportional character truncation rather than an exact page cut.
    """
    page_count = getattr(extracted.metadata, "page_count", None)
    if max_pages is None or not page_count or page_count <= max_pages:
        return extracted.content
    return extracted.content[: (len(extracted.content) * max_pages) // page_count]


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
            # The re-chunker only knows characters, not page boundaries -- every
            # sub-span inherits the parent prechunked span's page/heading info.
            "first_page": span.get("first_page"),
            "last_page": span.get("last_page"),
            "heading_path": span.get("heading_path"),
        }
        for sub in chunker.chunk(span["content"])
    ]


_WORD_CHAR_RE = re.compile(r"\w", re.UNICODE)


def _has_content(text: str) -> bool:
    """True if `text` has at least one real letter/digit, not just whitespace.

    `.strip()` isn't enough: marketing emails routinely pad their HTML with
    runs of U+034F (combining grapheme joiner) and soft hyphens as anti-
    clipping filler -- neither is whitespace by `str.isspace()`, so a span
    made entirely of them looks non-empty to `.strip()` while rendering as
    nothing visible.
    """
    return _WORD_CHAR_RE.search(text) is not None


def _spans_for(extracted: ExtractedText, chunker: "PlainTextChunker", max_pages: int | None = None) -> list[dict]:
    """Chunk boundaries either from xberg's own chunker (prechunked) or CLIR's now.

    `max_pages` caps how much of a long document gets embedded: prechunked
    spans carry real page numbers and are dropped past the cap; CLIR-chunked
    content falls back to `_truncate_to_pages`'s proportional cut.

    A content-free span (a page break, a signature separator, invisible
    email filler, ...) has nothing for BM25/kNN to match against, but would
    still surface as a hit via its parent file's denormalized `title` field
    -- an empty-looking result with no content to highlight. Dropped here
    rather than filtered at query time, since it's not worth embedding either.
    """
    if not extracted.prechunked:
        spans = [
            {"content": s.content, "start_offset": s.start_offset, "end_offset": s.end_offset}
            for s in chunker.chunk(_truncate_to_pages(extracted, max_pages))
        ]
        return [s for s in spans if _has_content(s["content"])]
    spans = [
        {
            "content": s.content,
            "start_offset": s.start_offset,
            "end_offset": s.end_offset,
            "first_page": s.first_page,
            "last_page": s.last_page,
            "heading_path": s.heading_path,
        }
        for s in extracted.prechunked
        if (max_pages is None or s.first_page is None or s.first_page <= max_pages) and _has_content(s.content)
    ]
    return [sub for span in spans for sub in _split_if_oversized(span, chunker) if _has_content(sub["content"])]


def _build_chunk(
    extracted: ExtractedText,
    dataset_id: str,
    filetype: str,
    sha256: str,
    span: dict,
    chunk_index: int,
    embedding: list[float],
) -> TextChunk:
    base = dict(
        dataset_id=dataset_id,
        file_id=extracted.file_id,
        sha256=sha256,
        duplicate_file_ids=[extracted.file_id],
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
        metadata = extracted.metadata.model_dump(exclude={"tables", "document_structure", "ocr_pages", "ocr_model"})
        # page_number/heading_path live on DocumentTextChunk itself, not on
        # DocumentMetadata -- only populated for prechunked (Kreuzberg) spans;
        # CLIR-chunked spans have no per-span page info by construction.
        return DocumentTextChunk(
            **base,
            **metadata,
            page_number=span.get("first_page"),
            heading_path=span.get("heading_path"),
        )
    if isinstance(extracted.metadata, EmailMetadata):
        return EmailTextChunk(**base, **extracted.metadata.model_dump())
    raise ValueError(f"No document/email metadata to embed for file_id={extracted.file_id!r}")


def _chunk_store(session: "AsyncSession", es_repo: ElasticsearchTextChunkRepository, *, use_pg: bool, ranker: str):
    """The chunk store the embed pipeline writes to, bound to `session`.

    `postgres` -> `PostgresChunkRetrievalRepository`. `elasticsearch` ->
    `ElasticsearchChunkRetrievalRepository`, which indexes to ES *and* mirrors
    chunk identity + spans (no embedding) into Postgres, since `mention.chunk_id`
    needs `chunk` rows to bisect against regardless of retrieval backend. Both
    expose the same `delete_by_file_id` / `bulk_index` / `attach_duplicate` /
    `list_by_file_id` surface `_consumer` / `dedupe_pending_text_embeddings` call.
    Must be rebuilt per session -- the producer and consumer each use their own
    `AsyncSession`, so a single pre-bound repo would write on one session while
    another commits.
    """
    if use_pg:
        from cipher.datastores.postgres.repositories.chunk_retrieval import PostgresChunkRetrievalRepository

        return PostgresChunkRetrievalRepository(session=session, text_ranker=ranker)

    from cipher.datastores.elasticsearch.repositories.chunk_retrieval import (
        ElasticsearchChunkRetrievalRepository,
    )

    return ElasticsearchChunkRetrievalRepository(client=es_repo.client, session=session, index=es_repo.index)


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
    skip_email_states: frozenset[EmailState] = DEFAULT_SKIP_EMAIL_STATES,
) -> int:
    """Resolve pending text embeddings whose content has already been embedded elsewhere.

    Two tiers, cheapest first:
    1. Same-dataset sibling: another file in this dataset with the same sha256
       already has indexed chunks -- attach this file to them (`duplicate_file_ids`)
       instead of storing/embedding a second copy. A dataset's file listing can
       legitimately contain the same content at multiple paths, so this is a real
       storage dedup, not just a compute shortcut.
    2. Cross-dataset: mirrors embed_images.py's image dedupe -- clone another
       dataset's already-embedded chunks (offsets/text/embeddings) onto this file's
       own chunks instead of re-running the GPU model. Storage isn't shared across
       datasets (a chunk's denormalized dataset_id/file_id/tags would otherwise leak
       one dataset's file identity into another's search results), only compute is.
    """
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    file_repo = PostgresFileRepository(session=session)
    extracted_text_repo = PostgresExtractedTextRepository(session=session)

    total = 0
    for group in _EMBED_GROUPS:
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

                attached = await es_repo.attach_duplicate(
                    dataset_id=item.resource["dataset_id"], sha256=sha256, file_id=file_id
                )
                if attached:
                    resolved.append(item.enrichment.id)
                    continue

                duplicate_chunks = await _find_embedded_duplicate(
                    file_repo=file_repo, es_repo=es_repo, file_id=file_id, sha256=sha256
                )
                if duplicate_chunks is None:
                    continue

                extracted = await extracted_text_repo.get_by_file_id(file_id)
                if extracted is None or _skip_email_state(extracted, skip_email_states):
                    # Skipped states are left pending for the producer, which
                    # marks them completed without indexing any chunks.
                    continue

                new_chunks = [
                    _build_chunk(
                        extracted=extracted,
                        dataset_id=item.resource["dataset_id"],
                        filetype=item.resource["filetype"],
                        sha256=sha256,
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
    max_pages: int | None,
    skip_email_states: frozenset[EmailState],
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

            if _skip_email_state(extracted, skip_email_states):
                await enrichment_repo.mark_completed_batch([item.enrichment.id])
                await session.commit()
                stats["skipped"] += 1
                pbar.update(1)
                continue

            try:
                spans = await loop.run_in_executor(_EXECUTOR, _spans_for, extracted, chunker, max_pages)
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
            _, failed_chunks = await es_repo.bulk_index(chunks, show_progress=False)
            if failed_chunks:
                # Files are still marked completed below (per-chunk retry
                # isn't worth the machinery here), but the gap must not be
                # silent -- reset-text + re-run is the recovery path.
                logger.error(f"{failed_chunks} of {len(chunks)} chunks failed to index this flush")
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
            # A failed file's remaining spans still count toward `seen` --
            # skipping them would leave `seen < total` forever, so the file
            # would never flush and its enrichment would stay PROCESSING.
            if not file_ctx.failed:
                try:
                    chunk = _build_chunk(
                        extracted=file_ctx.extracted,
                        dataset_id=file_ctx.item.resource["dataset_id"],
                        filetype=file_ctx.item.resource["filetype"],
                        sha256=file_ctx.item.resource["sha256"],
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
    max_pages: int | None = None,
    skip_email_states: frozenset[EmailState] = DEFAULT_SKIP_EMAIL_STATES,
) -> int:
    """Chunk (if needed) and embed a dataset's extracted text into the unified ES index.

    Runs documents and emails as separate producer/consumer pipelines (each
    with its own progress bar) so CPU tokenization and GPU embedding overlap
    within a group instead of serializing per file.

    `max_pages` caps how much of a long document gets embedded (see
    `_spans_for`); `skip_email_states` drops whole emails (spam by default)
    from the index. Both exist to keep chunk counts sane on large corpora.

    Returns the number of files embedded (not the number of chunks).
    """
    from clir.utils.text_chunk import PlainTextChunker

    _cfg = load_retrieval_config()
    _use_pg = _cfg.backend == RetrievalBackend.POSTGRES
    _ranker = _cfg.text_ranker.value
    es_repo = _chunk_store(session, es_repo, use_pg=_use_pg, ranker=_ranker)
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    _rebuild_search_indexes = False

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
    await dedupe_pending_text_embeddings(
        session=session, es_repo=es_repo, dataset_id=dataset_id, skip_email_states=skip_email_states
    )

    # Drop HNSW / tsvector / BM25 before a real load (rebuilt after): per-batch
    # maintenance across thousands of small flushes is slow, and an interrupted
    # write can leave HNSW / pg_search structures corrupt. Only when there's work.
    if _use_pg and hasattr(es_repo, "drop_search_indexes"):
        pending_total = 0
        for g in _EMBED_GROUPS:
            pending_total += await enrichment_repo.count_pending(
                enrichment_type=EnrichmentType.TEXT_EMBEDDING,
                enrichable_type=EnrichableType.FILE,
                dataset_id=dataset_id,
                filetype_group_filter=g,
            )
        if pending_total:
            await es_repo.drop_search_indexes()
            _rebuild_search_indexes = True

    # The chunker needs its own tokenizer instance: a fast (Rust) tokenizer is
    # a single mutably-borrowed object, and the consumer's model.encode()
    # re-borrows model.tokenizer (to set truncation/padding) concurrently with
    # the producer's chunking thread -- sharing one raises "Already borrowed".
    chunker = PlainTextChunker(
        tokenizer=deepcopy(model.tokenizer),
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        min_chunk_tokens=min_chunk_tokens,
    )

    engine = session.bind
    total_count = total_failed = total_chunks = 0

    for group in _EMBED_GROUPS:
        pending = await enrichment_repo.count_pending(
            enrichment_type=EnrichmentType.TEXT_EMBEDDING,
            enrichable_type=EnrichableType.FILE,
            dataset_id=dataset_id,
            filetype_group_filter=group,
        )
        if not pending:
            continue

        stats = {"files": 0, "failed": 0, "chunks": 0, "skipped": 0}
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
                            max_pages=max_pages,
                            skip_email_states=skip_email_states,
                            stats=stats,
                            pbar=pbar,
                        ),
                        _consumer(
                            queue=queue,
                            session=consumer_session,
                            model=model,
                            # rebind to the consumer's own session (see _chunk_store)
                            es_repo=_chunk_store(consumer_session, es_repo, use_pg=_use_pg, ranker=_ranker),
                            commit_batch_size=commit_batch_size,
                            stats=stats,
                            pbar=pbar,
                        ),
                    )

        logger.success(
            f"Embedded {stats['files']} {group}s into {stats['chunks']} chunks "
            f"({stats['failed']} failed, {stats['skipped']} skipped by state)"
        )
        total_count += stats["files"]
        total_failed += stats["failed"]
        total_chunks += stats["chunks"]

    logger.success(f"Embedded text for {total_count} files into {total_chunks} chunks ({total_failed} failed)")
    if _rebuild_search_indexes and hasattr(es_repo, "ensure_schema"):
        await es_repo.ensure_schema()  # rebuild HNSW / tsvector / BM25 now that the load is done
    return total_count


async def get_text_embedding_stats(session: "AsyncSession", dataset_id: str | None = None) -> dict:
    """Get enrichment stats for text embedding."""
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    return await enrichment_repo.get_enrichment_stats(
        enrichable_type=EnrichableType.FILE,
        dataset_id=dataset_id,
        enrichment_type=EnrichmentType.TEXT_EMBEDDING,
    )
