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
from cipher.orchestration.backfill_exif_locations import backfill_exif_locations
from cipher.orchestration.benchmark import benchmark_ingest, benchmark_storage
from cipher.orchestration.detect_faces import (
    detect_faces_workflow,
    get_face_detection_stats,
)
from cipher.orchestration.embed_images import embed_images_workflow, get_embedding_stats
from cipher.orchestration.embed_text import DEFAULT_SKIP_EMAIL_STATES, embed_text_workflow, get_text_embedding_stats
from cipher.orchestration.extract_documents import (
    DEFAULT_CHUNK_SIZE,
    Chunker,
    extract_documents_workflow,
    get_extraction_stats,
)
from cipher.orchestration.extract_emails import extract_emails_workflow
from cipher.orchestration.extract_events import extract_events_workflow, get_event_extraction_stats
from cipher.orchestration.extract_exif_locations import extract_exif_locations_workflow, get_exif_location_stats
from cipher.orchestration.extract_relationships import (
    extract_relationships_workflow,
    get_relationship_extraction_stats,
)
from cipher.orchestration.extract_selectors import extract_selectors_workflow, get_selector_extraction_stats
from cipher.orchestration.ingest import create_dataset, load_files
from cipher.orchestration.link_face_cooccurrence import (
    get_face_cooccurrence_stats,
    link_face_cooccurrence_workflow,
)
from cipher.orchestration.reset_entities import reset_entities
from cipher.orchestration.reset_events import reset_events
from cipher.orchestration.resolve_entities import resolve_entities_workflow
from cipher.orchestration.schema import create_tables
from cipher.orchestration.session import get_elasticsearch_client_context, get_session_context
from cipher.schemas._base.common import ModelDevice
from cipher.schemas.content.email import EmailState

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


@app.command("backfill-exif-locations")
def backfill_exif_locations_cmd(
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
):
    """Create map points for images that already have EXIF coordinates on their row."""

    async def _run():
        async with get_session_context() as session:
            scope = dataset_id
            if scope is None and dataset_name is not None:
                scope = await _resolve_dataset_id(session, dataset_id, dataset_name)
            written = await backfill_exif_locations(session=session, dataset_id=scope)
            typer.echo(f"{written} locations upserted")

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


@app.command("extract-locations")
def extract_locations_cmd(
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
):
    """Read EXIF GPS from a dataset's image files and write `location` rows (no model)."""

    async def _run():
        async with get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            count = await extract_exif_locations_workflow(session=session, dataset_id=resolved_id)
            stats = await get_exif_location_stats(session=session, dataset_id=resolved_id)
            logger.success(f"EXIF locations: processed {count} files; stats={stats}")

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
        int,
        typer.Option(help="Token budget per chunk when chunker=kreuzberg -- keep equal to embed-text's --chunk-size"),
    ] = DEFAULT_CHUNK_SIZE,
    model_dir: Annotated[
        Path | None,
        typer.Option(
            help="Local tokenizer directory for chunker=kreuzberg with token-based sizing (same dir as the embedding model)"
        ),
    ] = None,
    attachments_dir: Annotated[
        Path | None,
        typer.Option(
            help="Root directory for extracted email attachments, grouped by file ID. "
            "Default writes a '<stem>_attachments' directory next to each source email instead."
        ),
    ] = None,
    max_concurrent_extractions: Annotated[
        int | None,
        typer.Option(help="Cap xberg's internal batch parallelism -- default is xberg's own num_cpus*2"),
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
            email_count = await extract_emails_workflow(
                session=session, dataset_id=resolved_id, attachments_dir=attachments_dir
            )
            logger.success(f"Extracted text for {email_count} emails")
            doc_count = await extract_documents_workflow(
                session=session,
                dataset_id=resolved_id,
                chunker=chunker,
                tokenizer_model_dir=model_dir,
                chunk_size=chunk_size,
                max_concurrent_extractions=max_concurrent_extractions,
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
        int,
        typer.Option(
            help="Merge a final chunk below this many tokens into the previous one instead of embedding it alone"
        ),
    ] = 0,
    embed_batch_size: Annotated[
        int, typer.Option(help="Max spans per model.encode() call -- caps GPU memory use for heavily-chunked files")
    ] = 32,
    max_pages: Annotated[
        int | None,
        typer.Option(
            help="Only embed a document's first N pages -- exact for kreuzberg-prechunked spans (real page numbers), "
            "a proportional character cut otherwise. Keeps very long documents from flooding the index with chunks."
        ),
    ] = None,
    skip_email_state: Annotated[
        list[EmailState] | None,
        typer.Option(
            help="Email states to exclude from embedding entirely (repeat the flag to skip several); default: spam"
        ),
    ] = None,
):
    """Chunk (if needed) and embed a dataset's extracted text into the unified `text_chunks` search index.

    Run `extract-text` first -- this reads persisted `ExtractedText` rows,
    it doesn't parse files itself. Requires the `cli` extra (for `clir`) and
    Elasticsearch configured in `.env`.
    """
    from clir.models.pytorch import TextEmbeddingPytorchModel

    from cipher.datastores.elasticsearch.repositories.text_chunk import ElasticsearchTextChunkRepository
    from cipher.schemas.content.message import TEXT_EMBEDDING_DIMENSION

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
                    max_pages=max_pages,
                    skip_email_states=(
                        frozenset(skip_email_state) if skip_email_state is not None else DEFAULT_SKIP_EMAIL_STATES
                    ),
                )
                logger.success(f"Embedded text for {count} files")

    asyncio.run(_run())


@app.command("extract-selectors")
def extract_selectors_cmd(
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
):
    """Extract selectors from a dataset's emails into mentions + selector entities.

    Currently the email-header path only: every `from`/`sender`/`to`/`cc`/`bcc`
    address becomes an `email` selector entity plus a resolved `structured_field`
    mention, and each header display name an unresolved `person` mention. Run
    `extract-text` first -- this reads persisted `ExtractedText` metadata, it
    does not parse `.eml`/`.msg` files. Requires the `cli` extra (for
    `pyselectors`).
    """

    async def _run():
        async with get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            count = await extract_selectors_workflow(session=session, dataset_id=resolved_id)
            logger.success(f"Extracted selectors for {count} emails")

    asyncio.run(_run())


@app.command("extract-relationships")
def extract_relationships_cmd(
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
):
    """Build `communicates_with` edges between a dataset's email address selectors.

    Currently the email-header path only: an undirected edge between the `from`
    selector and each `to`/`cc`/`bcc` selector, `weight` = messages observed,
    `source = selector_inference`. Run `extract-selectors` first -- the edge
    endpoints are the selector entities it creates. Person `has_selector` edges
    wait on `resolve-entities`.
    """

    async def _run():
        async with get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            count = await extract_relationships_workflow(session=session, dataset_id=resolved_id)
            logger.success(f"Extracted relationships for {count} emails")

    asyncio.run(_run())


@app.command("link-face-cooccurrence")
def link_face_cooccurrence_cmd():
    """Rebuild `appears_in_photo_with` edges between people detected in the same image.

    Global (not dataset-scoped): an undirected person<->person edge per pair of
    people sharing a photo, where a face counts if it is assigned to a person or
    just has a pending `face_match` to them. `weight` = shared photos. Fully
    re-derived from current face state each run, so it also prunes edges whose
    matches were since rejected. Run after `detect-faces` and any face review.
    """

    async def _run():
        async with get_session_context() as session:
            counts = await link_face_cooccurrence_workflow(session=session)
            typer.echo(json.dumps(counts, indent=2))

    asyncio.run(_run())


@app.command("extract-events")
def extract_events_cmd(
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
):
    """Parse a dataset's `.ics` / calendar files into `event` rows (deterministic; no model).

    One row per VEVENT (`extractor = ics`), with unresolved participant / place
    links (`raw_name` / `raw_text`) for a later resolution sweep. LLM extraction
    over free-text email bodies is a separate future process. Requires the `cli`
    extra (for `pyparse`).
    """

    async def _run():
        async with get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            count = await extract_events_workflow(session=session, dataset_id=resolved_id)
            logger.success(f"Extracted events for {count} calendar files")

    asyncio.run(_run())


@app.command("resolve-entities")
def resolve_entities_cmd(
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
    min_mentions: Annotated[
        int,
        typer.Option(
            help="Create an entity for an unmatched name only if it has at least this many mentions (email-header names are always promoted)"
        ),
    ] = 2,
    no_create: Annotated[bool, typer.Option(help="Attach to existing entities only; never create new ones")] = False,
    skip_selector_links: Annotated[
        bool, typer.Option(help="Skip upserting person->selector has_selector edges from headers")
    ] = False,
):
    """Sweep unresolved name mentions -> entities (exact normalized-name match, then promote).

    A dataset-wide pass, not per-file: for each unresolved `name` mention it
    attaches to an existing entity with the same normalized name, else promotes
    trustworthy groups (email-header names, or >= --min-mentions) to a new
    provisional entity, else leaves them for the Review queue. Then links people
    to the address they sat next to in a header via `has_selector`.
    """

    async def _run():
        async with get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            counts = await resolve_entities_workflow(
                session=session,
                dataset_id=resolved_id,
                min_mentions=min_mentions,
                create=not no_create,
                link_selectors=not skip_selector_links,
            )
            typer.echo(json.dumps(counts, indent=2))

    asyncio.run(_run())


@app.command("reset-entities")
def reset_entities_cmd(
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
):
    """Delete a dataset's extraction-built entity layer -- the undo for `extract-selectors`.

    Drops mentions, the entity-match / relationship-candidate review queues,
    confirmed relationship edges, and every non-manual `entity` (+ detail),
    then clears the selector/entity/relationship extraction enrichments so a
    re-run reprocesses from scratch. Analyst-authored (`source = manual`)
    entities and standalone EXIF `location` rows are left intact.
    """

    async def _run():
        async with get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            counts = await reset_entities(session=session, dataset_id=resolved_id)
            typer.echo(json.dumps(counts, indent=2))

    asyncio.run(_run())


@app.command("reset-events")
def reset_events_cmd(
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
):
    """Delete a dataset's extraction-built events -- the undo for `extract-events`.

    Drops `event` rows (and cascading participant/place links) except those an
    analyst authored (`extractor = manual`) or confirmed (`is_verified`), then
    clears the EVENT_EXTRACTION enrichments so a re-run reprocesses from scratch.
    """

    async def _run():
        async with get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            counts = await reset_events(session=session, dataset_id=resolved_id)
            typer.echo(json.dumps(counts, indent=2))

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
    from cipher.schemas.ingestion.enrichment import EnrichmentType

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
    from cipher.schemas.ingestion.enrichment import EnrichmentType

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

            cooccurrence_stats = await get_face_cooccurrence_stats(session=session)
            typer.echo("Face co-occurrence (global):")
            typer.echo(f"  {cooccurrence_stats}")

            extraction_stats = await get_extraction_stats(session=session, dataset_id=resolved_id)
            typer.echo("Text extraction:")
            typer.echo(f"  {dict(extraction_stats.get(EnrichmentType.TEXT_EXTRACTION, {}))}")

            text_embedding_stats = await get_text_embedding_stats(session=session, dataset_id=resolved_id)
            typer.echo("Text embedding:")
            typer.echo(f"  {dict(text_embedding_stats.get(EnrichmentType.TEXT_EMBEDDING, {}))}")

            selector_stats = await get_selector_extraction_stats(session=session, dataset_id=resolved_id)
            typer.echo("Selector extraction:")
            typer.echo(f"  {dict(selector_stats.get(EnrichmentType.SELECTOR_EXTRACTION, {}))}")

            relationship_stats = await get_relationship_extraction_stats(session=session, dataset_id=resolved_id)
            typer.echo("Relationship extraction:")
            typer.echo(f"  {dict(relationship_stats.get(EnrichmentType.RELATIONSHIP_EXTRACTION, {}))}")

            event_stats = await get_event_extraction_stats(session=session, dataset_id=resolved_id)
            typer.echo("Event extraction:")
            typer.echo(f"  {dict(event_stats.get(EnrichmentType.EVENT_EXTRACTION, {}))}")

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


@app.command("benchmark-ingest")
def benchmark_ingest_cmd(
    directory: Annotated[Path, typer.Argument(exists=True, file_okay=False, help="Directory of files to ingest")],
    limit: Annotated[int | None, typer.Option(help="Max number of files to load")] = None,
    skip_emails: Annotated[bool, typer.Option(help="Skip the extract-emails stage")] = False,
    skip_documents: Annotated[bool, typer.Option(help="Skip the extract-documents stage")] = False,
    keep: Annotated[bool, typer.Option(help="Keep the benchmark dataset instead of deleting it after")] = False,
    report: Annotated[Path | None, typer.Option(help="Write the full JSON result to this path")] = None,
):
    """Benchmark real ingest throughput (filetyping, email/document extraction) over a local directory.

    Times the actual `load-files` / `extract-text` workflow functions
    end-to-end against a disposable dataset, rather than a synthetic
    workload -- so it reflects real filetyping/hashing/DB-write cost, and
    any pipeline optimization shows up here automatically. Use it to get a
    baseline before a change and compare after:

        uv run cipher benchmark-ingest ~/data/large-dir --report baseline.json
        # ...apply a change...
        uv run cipher benchmark-ingest ~/data/large-dir --report after.json
    """
    from filetyper.models.main import FileTyper

    async def _run():
        file_typer = FileTyper()
        async with get_session_context() as session:
            result = await benchmark_ingest(
                session=session,
                directory=directory,
                file_analyzer=file_typer.generate_from_local_path,
                limit=limit,
                skip_emails=skip_emails,
                skip_documents=skip_documents,
                cleanup=not keep,
            )
            typer.echo(json.dumps(result, indent=2))
            if report is not None:
                report.write_text(json.dumps(result, indent=2))
                typer.echo(f"\nWrote report to {report}")

    asyncio.run(_run())


if __name__ == "__main__":
    app()
