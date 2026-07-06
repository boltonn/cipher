"""Simple CLI for test-driving the ingestion + embedding + face-detection pipeline.

Deliberately minimal, and safe to run in any order or run twice: loading is
upsert-based (re-running on the same path is a no-op), and both the
embedding and face-detection commands dedupe by content hash before doing
any real work, so the same photo ingested more than once is only ever
embedded/detected once.
"""

import asyncio
import json
from pathlib import Path
from typing import Annotated

import typer
from loguru import logger

from cipher.datastores.postgres.repositories import PostgresDatasetRepository, PostgresEnrichmentRepository
from cipher.orchestration.benchmark import benchmark_storage
from cipher.orchestration.detect_faces import (
    detect_faces_workflow,
    get_face_detection_stats,
)
from cipher.orchestration.embed_images import embed_images_workflow, get_embedding_stats
from cipher.orchestration.embed_text import embed_text_workflow, get_text_embedding_stats
from cipher.orchestration.extract_documents import (
    DEFAULT_CHUNK_SIZE,
    Chunker,
    extract_documents_workflow,
    get_extraction_stats,
)
from cipher.orchestration.extract_emails import extract_emails_workflow
from cipher.orchestration.ingest import create_dataset, load_files
from cipher.orchestration.schema import create_tables
from cipher.orchestration.session import get_elasticsearch_client_context, get_session_context
from cipher.schemas.common import ModelDevice

app = typer.Typer(help="Test-drive ingestion, embedding, and face detection against a local dataset.")


async def _resolve_dataset_id(session, dataset_id: str | None, dataset_name: str | None) -> str:
    if dataset_id:
        return dataset_id
    if not dataset_name:
        raise typer.BadParameter("Provide --dataset-id or --dataset-name")
    dataset = await PostgresDatasetRepository(session=session).get_by_name(dataset_name)
    if not dataset:
        raise typer.BadParameter(f"Dataset not found: {dataset_name}")
    return dataset.id


@app.command("create-tables")
def create_tables_cmd():
    """Create all Postgres tables (idempotent; safe to run every time)."""

    async def _run():
        async with get_session_context() as session:
            await create_tables(session=session)
            logger.success("Tables ready")

    asyncio.run(_run())


@app.command("create-dataset")
def create_dataset_cmd(
    name: Annotated[str, typer.Option(help="Dataset name")],
    description: Annotated[str | None, typer.Option(help="Dataset description")] = None,
):
    """Create a new, empty dataset."""

    async def _run():
        async with get_session_context() as session:
            dataset = await create_dataset(session=session, name=name, description=description)
            typer.echo(dataset.id)

    asyncio.run(_run())


@app.command("load-files")
def load_files_cmd(
    path: Annotated[Path, typer.Argument(help="Local directory of files to load")],
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
    limit: Annotated[int | None, typer.Option(help="Max number of files to load")] = None,
):
    """Stage a directory of files into a dataset via file typing (File rows only; no analysis)."""
    from filetyper.models.main import FileTyper

    async def _run():
        file_typer = FileTyper()
        async with get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            count = await load_files(
                session=session,
                path=path,
                dataset_id=resolved_id,
                file_analyzer=file_typer.generate_from_local_path,
                limit=limit,
            )
            logger.success(f"Loaded {count} files into dataset {resolved_id}")

    asyncio.run(_run())


@app.command("embed-images")
def embed_images_cmd(
    model_dir: Annotated[Path, typer.Option(help="Path to the CLIP model directory")],
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
    device: Annotated[ModelDevice, typer.Option(help="Inference device")] = ModelDevice.CPU,
):
    """Run CLIP image embedding over a dataset's image files.

    Requires the `setfitcv` package's dependencies: run this from an
    environment where `uv sync --extra setfitcv` (or equivalent) has
    installed it. Independent of `detect-faces` — either can run first.
    """
    from setfitcv.model import CLIP

    async def _run():
        async with get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            model = CLIP(model_dir=model_dir, device=device.value)
            count = await embed_images_workflow(session=session, model=model, dataset_id=resolved_id)
            logger.success(f"Embedded {count} images")

    asyncio.run(_run())


@app.command("detect-faces")
def detect_faces_cmd(
    model_dir: Annotated[Path, typer.Option(help="Path to the InsightFace model directory")],
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
    device: Annotated[ModelDevice, typer.Option(help="Inference device")] = ModelDevice.CPU,
):
    """Run face detection over a dataset's image files.

    Requires the `face` package's dependencies (`analytics/face`): run this
    from an environment where `uv sync --extra face` (or equivalent) has
    installed InsightFace.
    """
    from face.api.deps import AsyncInsightFaceModel

    async def _run():
        async with get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            model = AsyncInsightFaceModel(model_dir=model_dir, device=device)
            count = await detect_faces_workflow(session=session, model=model, dataset_id=resolved_id)
            logger.success(f"Face detection processed {count} files")

    asyncio.run(_run())


@app.command("extract-text")
def extract_text_cmd(
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
    chunker: Annotated[
        Chunker, typer.Option(help="Chunker to use for documents (clir always chunks email text)")
    ] = Chunker.CLIR,
    chunk_size: Annotated[
        int, typer.Option(help="Token budget per chunk when chunker=kreuzberg -- keep equal to embed-text's --chunk-size")
    ] = DEFAULT_CHUNK_SIZE,
    model_dir: Annotated[
        Path | None,
        typer.Option(help="Local tokenizer directory for chunker=kreuzberg with token-based sizing (same dir as the embedding model)"),
    ] = None,
):
    """Extract text (and structure) from a dataset's eligible files.

    Runs emails first (pyparse) -- which also persists any attachments as
    their own files, linked via `parent_id` -- then documents (xberg,
    batched), so attachments discovered this run are swept up in the same
    pass. Requires the `pyxberg`/`pyparse[email]` packages: run this from an
    environment where `uv sync --extra cli` (cipher-orchestration's `cli`
    extra) has installed them.
    """

    async def _run():
        async with get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            email_count = await extract_emails_workflow(session=session, dataset_id=resolved_id)
            logger.success(f"Extracted text for {email_count} emails")
            doc_count = await extract_documents_workflow(
                session=session,
                dataset_id=resolved_id,
                chunker=chunker,
                tokenizer_model_dir=model_dir,
                chunk_size=chunk_size,
            )
            logger.success(f"Extracted text for {doc_count} document files")

    asyncio.run(_run())


@app.command("embed-text")
def embed_text_cmd(
    model_dir: Annotated[Path, typer.Option(help="Path to the text embedding model directory")],
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
    device: Annotated[ModelDevice, typer.Option(help="Inference device")] = ModelDevice.CPU,
    chunk_size: Annotated[
        int, typer.Option(help="Token budget per chunk -- keep equal to extract-text's --chunk-size")
    ] = DEFAULT_CHUNK_SIZE,
    chunk_overlap: Annotated[int, typer.Option(help="Token overlap between consecutive CLIR chunks")] = 0,
    min_chunk_tokens: Annotated[
        int, typer.Option(help="Merge a final chunk below this many tokens into the previous one instead of embedding it alone")
    ] = 0,
    embed_batch_size: Annotated[
        int, typer.Option(help="Max spans per model.encode() call -- caps GPU memory use for heavily-chunked files")
    ] = 32,
):
    """Chunk (if needed) and embed a dataset's extracted text into the unified `text_chunks` search index.

    Run `extract-text` first -- this reads persisted `ExtractedText` rows,
    it doesn't parse files itself. Requires the `cli` extra (for `clir`) and
    Elasticsearch configured in `.env`.
    """
    from clir.models.pytorch import TextEmbeddingPytorchModel

    from cipher.datastores.elasticsearch.repositories.text_chunk import ElasticsearchTextChunkRepository
    from cipher.schemas.message import TEXT_EMBEDDING_DIMENSION

    async def _run():
        model = TextEmbeddingPytorchModel(model_dir=model_dir, device=device.value)
        async with get_elasticsearch_client_context() as client:
            es_repo = ElasticsearchTextChunkRepository(client=client)
            # Same embedding dimension constant messages already index with --
            # keeps the door open to one day merging into a single search
            # surface without a dimension mismatch.
            await es_repo.create_index(embedding_size=TEXT_EMBEDDING_DIMENSION)

            async with get_session_context() as session:
                resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
                count = await embed_text_workflow(
                    session=session,
                    dataset_id=resolved_id,
                    model=model,
                    es_repo=es_repo,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                    min_chunk_tokens=min_chunk_tokens,
                    embed_batch_size=embed_batch_size,
                )
                logger.success(f"Embedded text for {count} files")

    asyncio.run(_run())


@app.command("reset-text")
def reset_text_cmd(
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
):
    """Delete a dataset's indexed text chunks and reset extraction/embedding to pending.

    Use after a chunking/embedding config change (chunk size, model, mapping)
    so `extract-text` and `embed-text` reprocess every file from scratch
    instead of skipping ones already marked complete under the old config.
    """
    from cipher.datastores.elasticsearch.repositories.text_chunk import ElasticsearchTextChunkRepository
    from cipher.schemas.enrichment import EnrichmentType

    async def _run():
        async with get_elasticsearch_client_context() as client:
            es_repo = ElasticsearchTextChunkRepository(client=client)
            async with get_session_context() as session:
                resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
                deleted_chunks = await es_repo.delete_by_dataset_id(resolved_id)

                enrichment_repo = PostgresEnrichmentRepository(session=session)
                reset_extraction = await enrichment_repo.delete_by_type(resolved_id, EnrichmentType.TEXT_EXTRACTION)
                reset_embedding = await enrichment_repo.delete_by_type(resolved_id, EnrichmentType.TEXT_EMBEDDING)

                logger.success(
                    f"Reset dataset {resolved_id}: deleted {deleted_chunks} indexed chunks, "
                    f"{reset_extraction} extraction + {reset_embedding} embedding enrichments cleared -- "
                    "re-run extract-text then embed-text to reprocess"
                )

    asyncio.run(_run())


@app.command("stats")
def stats(
    dataset_name: Annotated[str | None, typer.Option()] = None,
    dataset_id: Annotated[str | None, typer.Option()] = None,
):
    """Show file inventory and enrichment status for a dataset."""
    from cipher.datastores.postgres.repositories import PostgresFileRepository
    from cipher.schemas.enrichment import EnrichmentType

    async def _run():
        async with get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)

            inventory = await PostgresFileRepository(session=session).get_dataset_inventory(resolved_id)
            typer.echo("Files by type:")
            for group, info in inventory.items():
                typer.echo(f"  {group}: {info['count']} files ({info['size_bytes']} bytes)")

            embedding_stats = await get_embedding_stats(session=session, dataset_id=resolved_id)
            typer.echo("Image embedding:")
            typer.echo(f"  {dict(embedding_stats.get(EnrichmentType.IMAGE_EMBEDDING, {}))}")

            face_stats = await get_face_detection_stats(session=session, dataset_id=resolved_id)
            typer.echo("Face detection:")
            typer.echo(f"  {dict(face_stats.get(EnrichmentType.FACE_DETECTION, {}))}")

            extraction_stats = await get_extraction_stats(session=session, dataset_id=resolved_id)
            typer.echo("Text extraction:")
            typer.echo(f"  {dict(extraction_stats.get(EnrichmentType.TEXT_EXTRACTION, {}))}")

            text_embedding_stats = await get_text_embedding_stats(session=session, dataset_id=resolved_id)
            typer.echo("Text embedding:")
            typer.echo(f"  {dict(text_embedding_stats.get(EnrichmentType.TEXT_EMBEDDING, {}))}")

    asyncio.run(_run())


@app.command("benchmark-storage")
def benchmark_storage_cmd(
    n: Annotated[int, typer.Option(help="Number of synthetic rows to upsert/read")] = 100,
    content_chars: Annotated[
        int, typer.Option(help="Characters of extracted text per row (~35k approximates a 10-page OCR'd PDF)")
    ] = 35_000,
    tables_per_row: Annotated[int, typer.Option(help="Fake tables to attach per row")] = 2,
    keep: Annotated[bool, typer.Option(help="Keep the benchmark dataset instead of deleting it after")] = False,
):
    """Benchmark Postgres upsert/read latency and on-disk size for cached extracted text.

    Answers whether caching extraction output in Postgres (so nothing
    downstream re-runs OCR/parsing) is itself a speed or storage concern.
    Compare the write/read numbers here against `pyxberg benchmark`'s
    per-file extraction time -- if extraction takes tens of milliseconds
    and a Postgres upsert takes a fraction of that, the cache isn't what's
    slow.
    """

    async def _run():
        async with get_session_context() as session:
            result = await benchmark_storage(
                session=session, n=n, content_chars=content_chars, n_tables=tables_per_row, cleanup=not keep
            )
            typer.echo(json.dumps(result, indent=2))

    asyncio.run(_run())


if __name__ == "__main__":
    app()
