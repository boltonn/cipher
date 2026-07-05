"""Text embedding workflow (Stage 2) -- chunk + embed extracted text into the unified ES index.

Reads persisted `ExtractedText` rows (written by extract_emails.py /
extract_documents.py) rather than re-parsing files. When prechunked spans
already exist (chunker=kreuzberg was used at extraction time), those are
embedded directly -- no second split. Otherwise CLIR's `PlainTextChunker`
splits the extracted text now, using the same `chunk_size` as
extract_documents.py's xberg chunker so chunk boundaries don't drift
depending on which chunker produced them.
"""

from time import perf_counter
from typing import TYPE_CHECKING, Any

import anyio
from loguru import logger

from cipher.datastores.elasticsearch.repositories.text_chunk import ElasticsearchTextChunkRepository
from cipher.datastores.postgres.repositories import PostgresEnrichmentRepository, PostgresExtractedTextRepository
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


def _spans_for(extracted: ExtractedText, chunker: "PlainTextChunker") -> list[dict]:
    """Chunk boundaries either from xberg's own chunker (prechunked) or CLIR's now."""
    if extracted.prechunked:
        return [
            {"content": s.content, "start_offset": s.start_offset, "end_offset": s.end_offset}
            for s in extracted.prechunked
        ]
    return [
        {"content": s.content, "start_offset": s.start_offset, "end_offset": s.end_offset}
        for s in chunker.chunk(extracted.content)
    ]


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
        return DocumentTextChunk(**base, **extracted.metadata.model_dump())
    if isinstance(extracted.metadata, EmailMetadata):
        return EmailTextChunk(**base, **extracted.metadata.model_dump())
    raise ValueError(f"No document/email metadata to embed for file_id={extracted.file_id!r}")


def _run_chunk_and_encode(
    extracted: ExtractedText,
    dataset_id: str,
    chunker: "PlainTextChunker",
    model: "TextEmbeddingPytorchModel",
) -> "list[Any]":
    """CPU/GPU-bound worker: split (if needed) and embed one file's extracted text."""
    spans = _spans_for(extracted, chunker)
    if not spans:
        return []
    embeddings = model.encode([s["content"] for s in spans], task="retrieval", is_query=False)
    return [
        _build_chunk(extracted, dataset_id, span, i, emb.tolist())
        for i, (span, emb) in enumerate(zip(spans, embeddings, strict=True))
    ]


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
) -> int:
    """Chunk (if needed) and embed a dataset's extracted text into the unified ES index.

    Returns the number of files embedded (not the number of chunks).
    """
    from clir.utils.text_chunk import PlainTextChunker

    logger.debug(f"embed_text_workflow starting for dataset {dataset_id} (chunk_size={chunk_size})")
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

    extracted_text_repo = PostgresExtractedTextRepository(session=session)
    chunker = PlainTextChunker(
        tokenizer=model.tokenizer, chunk_size=chunk_size, chunk_overlap=chunk_overlap, min_chunk_tokens=min_chunk_tokens
    )

    start = perf_counter()
    count = 0

    for group in _TEXT_GROUPS:
        logger.debug(f"Embedding {group} files for dataset {dataset_id}")
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

            logger.debug(f"Processing batch of {len(batch)} pending {group} files")
            await enrichment_repo.mark_processing(enrichment_ids=[item.enrichment.id for item in batch])
            await session.commit()

            completed, failed = [], []
            all_chunks: list[TextChunk] = []
            for item in batch:
                try:
                    extracted = await extracted_text_repo.get_by_file_id(item.resource["id"])
                    if extracted is None:
                        raise ValueError("No extracted text yet for this file")

                    logger.debug(f"Chunking and embedding file {item.resource['id']} ({item.resource['filename']!r})")
                    chunks = await anyio.to_thread.run_sync(
                        _run_chunk_and_encode, extracted, item.resource["dataset_id"], chunker, model
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
                await es_repo.bulk_index(all_chunks)

            if completed:
                await enrichment_repo.mark_completed_batch(completed)
            if failed:
                await enrichment_repo.mark_failed_batch(failed, increment_retry=True)
            await session.commit()

            count += len(completed)
            logger.info(f"Embedded {len(completed)} {group} files ({count} total)")

    total_ms = int((perf_counter() - start) * 1000)
    logger.success(f"Embedded text for {count} files in {total_ms}ms")
    return count


async def get_text_embedding_stats(session: "AsyncSession", dataset_id: str | None = None) -> dict:
    """Get enrichment stats for text embedding."""
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    return await enrichment_repo.get_enrichment_stats(
        enrichable_type=EnrichableType.FILE,
        dataset_id=dataset_id,
        enrichment_type=EnrichmentType.TEXT_EMBEDDING,
    )
