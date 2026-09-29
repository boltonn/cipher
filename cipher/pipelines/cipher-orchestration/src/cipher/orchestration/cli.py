"""Simple CLI for test-driving the ingestion + embedding + face-detection pipeline.

Deliberately minimal, and safe to run in any order or run twice: loading is
upsert-based (re-running on the same path is a no-op), and both the
embedding and face-detection commands dedupe by content hash before doing
any real work, so the same photo ingested more than once is only ever
embedded/detected once.
"""

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import typer
from loguru import logger

from cipher.datastores.postgres.repositories import (
    PostgresDatasetRepository,
    PostgresEnrichmentRepository,
    PostgresFaceRepository,
    PostgresGraphRepository,
)
from cipher.orchestration.backfill_entity_name_keys import backfill_entity_name_keys_workflow
from cipher.orchestration.backfill_exif_locations import backfill_exif_locations
from cipher.orchestration.benchmark import benchmark_ingest, benchmark_storage
from cipher.orchestration.cluster_faces import cluster_faces_workflow, reset_face_clusters
from cipher.orchestration.dedupe_entities import dedupe_entities_workflow
from cipher.orchestration.embed_images import embed_images_workflow, get_embedding_stats
from cipher.orchestration.embed_text import DEFAULT_SKIP_EMAIL_STATES, embed_text_workflow, get_text_embedding_stats
from cipher.orchestration.environments import ensure_stage_env
from cipher.orchestration.extract_contact_entities import extract_contact_entities_workflow
from cipher.orchestration.extract_documents import (
    DEFAULT_CHUNK_SIZE,
    Chunker,
    OcrBackend,
    XbergOcr,
    extract_documents_workflow,
    get_extraction_stats,
)
from cipher.orchestration.extract_emails import extract_emails_workflow
from cipher.orchestration.extract_entities import extract_entities_workflow, get_entity_extraction_stats
from cipher.orchestration.extract_events import (
    TEXT_EVENT_GROUPS_ALL,
    TEXT_EVENT_GROUPS_EMAIL,
    extract_events_workflow,
    extract_text_events_workflow,
    get_event_extraction_stats,
)
from cipher.orchestration.extract_exif_locations import extract_exif_locations_workflow, get_exif_location_stats
from cipher.orchestration.extract_llm import (
    DEFAULT_CONCURRENCY,
    DEFAULT_MAX_LLM_PASS_FILES,
    LlmPassTooLargeError,
    extract_llm_workflow,
)
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
from cipher.orchestration.match_faces import match_faces_workflow, reset_face_matches
from cipher.orchestration.refresh_selectors import refresh_selectors_workflow
from cipher.orchestration.reset_entities import reset_entities
from cipher.orchestration.reset_events import reset_events
from cipher.orchestration.resolve_entities import resolve_entities_workflow
from cipher.orchestration.resolve_event_links import resolve_event_links_workflow
from cipher.orchestration.run_recorder import record_run
from cipher.orchestration.schema import create_tables
from cipher.orchestration.session import get_elasticsearch_client_context, get_session_context
from cipher.orchestration.sync_chunk_entities import sync_chunk_entities_workflow
from cipher.schemas._base.common import ModelDevice
from cipher.schemas.content.email import EmailState
from cipher.schemas.graph.entity_resolution import EntityResolutionConfig
from cipher.schemas.identity.face import DEFAULT_FACE_REJECT_SIMILARITY
from cipher.schemas.ingestion.enrichment import EnrichmentType
from cipher.schemas.ingestion.estimation import WorkUnit

app = typer.Typer(help="Test-drive ingestion, embedding, and face detection against a local dataset.")


@asynccontextmanager
async def _text_chunk_es_repo():
    """The ES `text_chunks` repo when `RETRIEVAL__BACKEND=elasticsearch`, else None (ES never opened)."""
    from cipher.utils.retrieval import RetrievalBackend, load_retrieval_config

    if load_retrieval_config().backend == RetrievalBackend.POSTGRES:
        yield None
        return
    from cipher.datastores.elasticsearch.repositories.text_chunk import ElasticsearchTextChunkRepository
    from cipher.schemas.content.message import TEXT_EMBEDDING_DIMENSION

    async with get_elasticsearch_client_context() as client:
        es_repo = ElasticsearchTextChunkRepository(client=client)
        await es_repo.create_index(embedding_size=TEXT_EMBEDDING_DIMENSION)
        yield es_repo


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
    ensure_stage_env("staging")
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

    Independent of `detect-faces` -- either can run first.
    """
    ensure_stage_env("image-embedding")
    from setfitcv.model import CLIP

    async def _run():
        async with get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            model = CLIP(model_dir=model_dir, device=device.value)
            async with record_run(
                enrichment_type=EnrichmentType.IMAGE_EMBEDDING,
                dataset_id=resolved_id,
                device=device.value,
                unit=WorkUnit.IMAGE,
            ) as run:
                run.units = await embed_images_workflow(session=session, model=model, dataset_id=resolved_id)
            logger.success(f"Embedded {run.units} images")

    asyncio.run(_run())


@app.command("extract-locations")
def extract_locations_cmd(
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
):
    """Read EXIF GPS from a dataset's image files and write `location` rows (no model)."""
    ensure_stage_env("exif-location")

    async def _run():
        async with get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            async with record_run(
                enrichment_type=EnrichmentType.EXIF_LOCATION,
                dataset_id=resolved_id,
                device="na",
                unit=WorkUnit.IMAGE,
            ) as run:
                run.units = await extract_exif_locations_workflow(session=session, dataset_id=resolved_id)
            stats = await get_exif_location_stats(session=session, dataset_id=resolved_id)
            logger.success(f"EXIF locations: processed {run.units} files; stats={stats}")

    asyncio.run(_run())


@app.command("detect-faces")
def detect_faces_cmd(
    model_dir: Annotated[Path, typer.Option(help="Path to the InsightFace model directory")],
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
    device: Annotated[ModelDevice, typer.Option(help="Inference device")] = ModelDevice.CPU,
):
    """Run face detection over a dataset's image files."""
    ensure_stage_env("face-detection")
    from face.api.deps import AsyncInsightFaceModel

    from cipher.orchestration.detect_faces import detect_faces_workflow

    async def _run():
        async with get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            model = AsyncInsightFaceModel(model_dir=model_dir, device=device)
            async with record_run(
                enrichment_type=EnrichmentType.FACE_DETECTION,
                dataset_id=resolved_id,
                device=device.value,
                unit=WorkUnit.IMAGE,
            ) as run:
                run.units = await detect_faces_workflow(session=session, model=model, dataset_id=resolved_id)
            logger.success(f"Face detection processed {run.units} files")

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
    ocr_backend: Annotated[
        OcrBackend, typer.Option(help="OCR for image-based PDF pages during extraction (none = record them only)")
    ] = OcrBackend.EASYOCR,
    ocr_language: Annotated[
        list[str] | None, typer.Option(help="OCR language code, repeatable (EasyOCR: en, fr...; Tesseract: eng...)")
    ] = None,
    ocr_model_dir: Annotated[
        Path | None,
        typer.Option(envvar="EASYOCR_MODEL_DIR", help="Pre-downloaded EasyOCR weights, so OCR never downloads"),
    ] = None,
):
    """Extract text (and structure) from a dataset's eligible files.

    Runs emails first (pyparse) -- which also persists any attachments as
    their own files, linked via `parent_id` -- then documents (xberg,
    batched), so attachments discovered this run are swept up in the same
    pass. PDF pages without a usable text layer are recorded as
    `metadata.image_pages` and OCR'd inline (EasyOCR by default); re-run just
    those with a stronger model via `cipher ocr`.
    """
    ensure_stage_env("text-extraction")
    ocr = XbergOcr(backend=ocr_backend, languages=ocr_language or ["en"], model_dir=ocr_model_dir)
    if ocr_backend == OcrBackend.EASYOCR and ocr_model_dir is None:
        logger.warning("No --ocr-model-dir / EASYOCR_MODEL_DIR -- EasyOCR will try to download its weights")

    async def _run():
        async with get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            async with record_run(
                enrichment_type=EnrichmentType.TEXT_EXTRACTION,
                dataset_id=resolved_id,
                device="na",
                unit=WorkUnit.TEXT_FILE,
                params={"chunker": chunker.value, "chunk_size": chunk_size, "ocr_backend": ocr_backend.value},
            ) as run:
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
                    ocr=ocr,
                )
                logger.success(f"Extracted text for {doc_count} document files")
                run.units = email_count + doc_count

    asyncio.run(_run())


@app.command("ocr")
def ocr_cmd(
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
    filetype: Annotated[
        list[str] | None,
        typer.Option(help="Filetype(s) to OCR, repeatable (e.g. pdf, heif). Default: every PDF + supported image"),
    ] = None,
    service_url: Annotated[
        list[str] | None,
        typer.Option(help="pyocr service URL, repeatable -- one per GPU (`make start-vllm-all`). Default :8010"),
    ] = None,
    concurrency: Annotated[
        int, typer.Option(help="Files in flight across all services; each decodes its files' pages together")
    ] = 32,
    min_chars: Annotated[int, typer.Option(help="PDF pages with fewer text-layer word chars are OCR'd")] = 20,
    force: Annotated[bool, typer.Option(help="OCR every PDF page, not just image-based ones")] = False,
    figures: Annotated[bool, typer.Option(help="Also locate + caption figures (grounding prompt)")] = False,
    clip_model_dir: Annotated[
        Path | None, typer.Option(help="CLIP model dir: only OCR images matching --clip-tag (needs embed-images)")
    ] = None,
    clip_tag: Annotated[list[str] | None, typer.Option(help="Text-bearing CLIP tag, repeatable")] = None,
    clip_negative_tag: Annotated[list[str] | None, typer.Option(help="Competing non-text CLIP tag, repeatable")] = None,
    clip_threshold: Annotated[float, typer.Option(help="Min probability mass on --clip-tag to OCR an image")] = 0.5,
):
    """OCR image-based PDF pages and images into extracted text (run after extract-text).

    Needs the pyocr service running (`make start-vllm` in analytics/pyocr). With
    --clip-model-dir, images are filtered by zero-shot CLIP tags scored against the
    embeddings `embed-images` already stored, so only likely text-bearing images
    (screenshots, scans, receipts, signs...) are sent to the model.
    """
    ensure_stage_env("ocr")
    from pyocr.client import OcrClient

    from cipher.orchestration.ocr import (
        DEFAULT_CLIP_NEGATIVE_TAGS,
        DEFAULT_CLIP_TAGS,
        ClipTagFilter,
        get_ocr_stats,
        ocr_workflow,
    )

    clip_filter = None
    if clip_model_dir:
        from setfitcv.model import CLIP

        clip_filter = ClipTagFilter.from_model(
            model=CLIP(model_dir=clip_model_dir, device="cpu", warmup=False),
            tags=clip_tag or list(DEFAULT_CLIP_TAGS),
            negative_tags=clip_negative_tag or list(DEFAULT_CLIP_NEGATIVE_TAGS),
            threshold=clip_threshold,
        )

    async def _run():
        client = OcrClient(base_urls=service_url)
        try:
            async with get_session_context() as session:
                resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
                async with record_run(
                    enrichment_type=EnrichmentType.OCR,
                    dataset_id=resolved_id,
                    device="cuda",
                    unit=WorkUnit.FILE,
                    params={"filetypes": filetype, "clip": clip_filter is not None, "force": force, "figures": figures},
                ) as run:
                    run.units = await ocr_workflow(
                        session=session,
                        client=client,
                        dataset_id=resolved_id,
                        filetypes=filetype,
                        clip_filter=clip_filter,
                        concurrency=concurrency,
                        min_chars=min_chars,
                        force=force,
                        figures=figures,
                    )
                logger.success(f"OCR stats: {await get_ocr_stats(session=session, dataset_id=resolved_id)}")
        finally:
            await client.aclose()

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
    """Chunk (if needed) and embed a dataset's extracted text into the chunk store (`RETRIEVAL__BACKEND`).

    Run `extract-text` first -- this reads persisted `ExtractedText` rows,
    it doesn't parse files itself. Elasticsearch is only opened when
    `RETRIEVAL__BACKEND=elasticsearch`.
    """
    ensure_stage_env("text-embedding")
    from clir.models.pytorch import TextEmbeddingPytorchModel

    async def _run():
        model = TextEmbeddingPytorchModel(model_dir=model_dir, device=device.value)
        async with _text_chunk_es_repo() as es_repo, get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            async with record_run(
                enrichment_type=EnrichmentType.TEXT_EMBEDDING,
                dataset_id=resolved_id,
                device=device.value,
                unit=WorkUnit.TEXT_FILE,
                params={"chunk_size": chunk_size, "max_pages": max_pages},
            ) as run:
                run.units = await embed_text_workflow(
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
            logger.success(f"Embedded text for {run.units} files")

    asyncio.run(_run())


@app.command("extract-selectors")
def extract_selectors_cmd(
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
):
    """Extract selectors from every text-bearing file into mentions + selector entities.

    Two passes per file: email-header participants become `email` selector
    entities + resolved `structured_field` mentions (with an unresolved name
    mention per display name), and `pyselectors` runs over the extracted body
    text for phone / email / ip / iban / imei / crypto / social-handle spans
    with real offsets, kind attributes, and a context-scored confidence. Run
    `extract-text` first -- this reads persisted `ExtractedText`, it does not
    parse source files.
    """

    async def _run():
        async with get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            async with record_run(
                enrichment_type=EnrichmentType.SELECTOR_EXTRACTION,
                dataset_id=resolved_id,
                device="na",
                unit=WorkUnit.TEXT_FILE,
            ) as run:
                run.units = await extract_selectors_workflow(session=session, dataset_id=resolved_id)
            logger.success(f"Extracted selectors for {run.units} files")

    asyncio.run(_run())


@app.command("backfill-mention-chunks")
def backfill_mention_chunks_cmd(
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
):
    """Set `mention.chunk_id` on a dataset's text mentions (Postgres retrieval backend).

    Extraction now sets `chunk_id` inline, so this is only for datasets extracted
    before that, or after a re-embed changed chunk boundaries. Set-based; idempotent.
    """
    from cipher.datastores.postgres.repositories.mention import PostgresMentionRepository

    async def _run():
        async with get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            n = await PostgresMentionRepository(session=session).backfill_chunk_ids(dataset_id=resolved_id)
            typer.echo(f"set chunk_id on {n} mentions")

    asyncio.run(_run())


@app.command("sync-chunk-entities")
def sync_chunk_entities_cmd(
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
    purge: Annotated[bool, typer.Option(help="Clear entity fields on chunks with no mentions first")] = False,
):
    """[elasticsearch retrieval backend only] Denormalize mentions onto the `text_chunks` ES index.

    Obsolete when `RETRIEVAL__BACKEND=postgres` -- there search joins
    `mention.chunk_id` live (see `backfill-mention-chunks`). For the ES backend:
    run after `extract-selectors` / `extract-entities`; each chunk doc gets the
    `entity_ids` / `entity_types` / `selector_types` / `selector_subtypes` /
    `mention_count` of the mentions anchored in its span. Idempotent; use
    `--purge` after `reset-entities`.
    """

    async def _run():
        async with get_session_context() as session, get_elasticsearch_client_context() as es_client:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            summary = await sync_chunk_entities_workflow(
                session=session, es_client=es_client, dataset_id=resolved_id, purge=purge
            )
            typer.echo(json.dumps(summary, indent=2))

    asyncio.run(_run())


@app.command("extract-relationships")
def extract_relationships_cmd(
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
    rebuild: Annotated[
        bool, typer.Option(help="Drop and recompute this dataset's email edges (e.g. pre-`emailed` ones)")
    ] = False,
):
    """Build directed `emailed` edges between a dataset's email address selectors.

    Currently the email-header path only: an edge from the `from` selector to each
    `to`/`cc`/`bcc` selector, `weight` = emails sent that way, `source =
    selector_inference`. Run `extract-selectors` first -- the edge endpoints are the
    selector entities it creates. Person `has_selector` edges wait on `resolve-entities`.
    """

    async def _run():
        async with get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            async with record_run(
                enrichment_type=EnrichmentType.RELATIONSHIP_EXTRACTION,
                dataset_id=resolved_id,
                device="na",
                unit=WorkUnit.LLM_FILE,
            ) as run:
                run.units = await extract_relationships_workflow(
                    session=session, dataset_id=resolved_id, rebuild=rebuild
                )
            logger.success(f"Extracted relationships for {run.units} emails")

    asyncio.run(_run())


@app.command("link-face-cooccurrence")
def link_face_cooccurrence_cmd(
    min_verified_photos: Annotated[
        int,
        typer.Option(
            help="Link two already-identified people only if they share at least this many photos "
            "(a pair with an unconfirmed/pending face match is always linked). Set to 1 to keep every co-occurrence."
        ),
    ] = 2,
):
    """Rebuild `appears_in_photo_with` edges between people detected in the same image.

    Global (not dataset-scoped): an undirected person<->person edge per pair of
    people sharing a photo, where a face counts if it is assigned to a person or
    just has a pending `face_match` to them. `weight` = shared photos. Fully
    re-derived from current face state each run, so it also prunes edges whose
    matches were since rejected or that dropped below `--min-verified-photos`.
    Run after `detect-faces` and any face review.
    """

    async def _run():
        async with get_session_context() as session:
            counts = await link_face_cooccurrence_workflow(session=session, min_verified_photos=min_verified_photos)
            typer.echo(json.dumps(counts, indent=2))

    asyncio.run(_run())


@app.command("match-faces")
def match_faces_cmd(
    dataset_name: Annotated[str | None, typer.Option(help="Scope candidate faces to this dataset")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Scope candidate faces to this dataset ID")] = None,
    similarity: Annotated[float, typer.Option(help="Min cosine similarity to propose a match")] = 0.61,
    verified_only: Annotated[
        bool,
        typer.Option(
            help="Match only against analyst-verified people (default: all people with a representative face)"
        ),
    ] = False,
    per_face_limit: Annotated[int, typer.Option(help="Max candidate faces pulled per representative face")] = 500,
    no_cooccurrence: Annotated[
        bool, typer.Option(help="Skip refreshing appears_in_photo_with for the touched faces")
    ] = False,
    reset: Annotated[
        bool, typer.Option(help="Undo: delete pending machine-proposed matches (analyst decisions kept)")
    ] = False,
):
    """Propose pending face->person matches from every person's representative faces.

    The batch counterpart to the reactive matcher that runs when an analyst adds
    a reference face. Person-level (O(representative faces), not O(all faces)):
    for each representative face it KNN-searches still-unassigned faces above
    --similarity and records a pending `face_match` for review -- nothing is
    auto-assigned. Idempotent; run it after `detect-faces` and before
    `cluster-faces`. Confirm/reject in the Faces UI.
    """

    async def _run():
        async with get_session_context() as session:
            resolved_id = (
                await _resolve_dataset_id(session, dataset_id, dataset_name) if (dataset_id or dataset_name) else None
            )
            if reset:
                counts = await reset_face_matches(session=session, dataset_id=resolved_id)
            else:
                counts = await match_faces_workflow(
                    session=session,
                    dataset_id=resolved_id,
                    min_similarity=similarity,
                    verified_only=verified_only,
                    per_face_limit=per_face_limit,
                    rebuild_cooccurrence=not no_cooccurrence,
                )
            typer.echo(json.dumps(counts, indent=2))

    asyncio.run(_run())


@app.command("reject-similar-faces")
def reject_similar_faces_cmd(
    similarity: Annotated[
        float, typer.Option(help="Min cosine similarity to a manually rejected face to auto-reject")
    ] = DEFAULT_FACE_REJECT_SIMILARITY,
):
    """Auto-reject unassigned faces resembling ones an analyst marked "not a face".

    Also releases automatic rejections no manual exemplar supports at --similarity,
    so re-running with a higher value tightens the set. Rejecting in the UI and
    `detect-faces` already do this incrementally; use this after tuning.
    """

    async def _run():
        async with get_session_context() as session:
            face_repo = PostgresFaceRepository(session=session)
            released = await face_repo.release_unsupported_auto_rejections(min_similarity=similarity)
            rejected_ids = await face_repo.auto_reject_similar(min_similarity=similarity)
            await PostgresGraphRepository(session=session).recompute_face_cooccurrence_for_faces(rejected_ids)
            typer.echo(json.dumps({"auto_rejected": len(rejected_ids), "released": released}, indent=2))

    asyncio.run(_run())


@app.command("cluster-faces")
def cluster_faces_cmd(
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to (persons stay global)")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
    similarity: Annotated[float, typer.Option(help="Min cosine similarity for a face-to-face cluster edge")] = 0.61,
    k: Annotated[int, typer.Option(help="Nearest neighbours considered per face")] = 20,
    min_images: Annotated[
        int, typer.Option(help="Mint a person only for a cluster spanning at least this many distinct images")
    ] = 3,
    min_faces: Annotated[int, typer.Option(help="...and at least this many faces")] = 2,
    max_faces: Annotated[int, typer.Option(help="Safety cap on unassigned faces considered per run")] = 200_000,
    no_merge: Annotated[
        bool, typer.Option(help="Always create a fresh person; never merge a cluster into an existing one")
    ] = False,
    no_cooccurrence: Annotated[
        bool, typer.Option(help="Skip rebuilding appears_in_photo_with edges afterwards")
    ] = False,
    reset: Annotated[
        bool, typer.Option(help="Undo: drop unverified face_clustering persons and unlink their faces")
    ] = False,
    reset_verified: Annotated[
        bool, typer.Option(help="With --reset, also drop face_clustering persons an analyst verified")
    ] = False,
):
    """Cluster unassigned faces into unnamed persons (source = face_clustering).

    A dataset-wide sweep: builds a kNN similarity graph off the face HNSW index,
    union-finds it into clusters, and creates one unnamed / unverified `person`
    per cluster that spans >= --min-images images (and >= --min-faces faces),
    assigning every face in it. Smaller clusters and singletons stay unassigned.
    Incremental -- only touches faces without a person; a new cluster near an
    existing clustering person merges into it unless --no-merge. Rename / merge /
    split in the Persons UI (filter with ?source=face_clustering / ?unnamed=true).
    """

    async def _run():
        async with get_session_context() as session:
            if reset:
                counts = await reset_face_clusters(session=session, include_verified=reset_verified)
                typer.echo(json.dumps(counts, indent=2))
                return
            resolved_id = (
                await _resolve_dataset_id(session, dataset_id, dataset_name) if (dataset_id or dataset_name) else None
            )
            counts = await cluster_faces_workflow(
                session=session,
                dataset_id=resolved_id,
                similarity=similarity,
                k=k,
                min_images=min_images,
                min_faces=min_faces,
                max_faces=max_faces,
                merge_into_existing=not no_merge,
                rebuild_cooccurrence=not no_cooccurrence,
            )
            typer.echo(json.dumps(counts, indent=2))

    asyncio.run(_run())


@app.command("extract-events")
def extract_events_cmd(
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
    llm: Annotated[
        bool,
        typer.Option(help="Also run LLM extraction over email bodies (needs pyprompt + an LLM__* config)"),
    ] = False,
    llm_only: Annotated[bool, typer.Option(help="Run only the LLM text-body path, skip the .ics parse")] = False,
    docs: Annotated[bool, typer.Option(help="LLM pass also scans document files (PDF/DOCX), not just email")] = False,
    model: Annotated[str | None, typer.Option(help="Override the configured LLM model id")] = None,
):
    """Parse a dataset's `.ics` files into `event` rows (deterministic), optionally plus an LLM pass.

    `.ics`: one row per VEVENT (`extractor = ics`), carrying the iCalendar fields
    (`uid`, `recurrence_rule`, `categories`, `sequence`, `url`, `sensitivity`,
    `GEO` -> a geocoded place). `--llm`: also run `pyprompt` over email bodies
    (`--docs` adds documents) anchored to each file's authored date
    (`extractor = llm`, typed `details` / `url` / `confidence`), deduped on `uid`
    then `(title, start date)` / `(type, start date, place)`. Both leave
    unresolved participant / place links for `resolve-event-links`. Requires the
    `event-extraction` stage (for `pyparse`); `--llm` also needs an `LLM__*` config.
    """
    ensure_stage_env("event-extraction")

    async def _run():
        async with get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            async with record_run(
                enrichment_type=EnrichmentType.EVENT_EXTRACTION,
                dataset_id=resolved_id,
                device="na",
                unit=WorkUnit.LLM_FILE,
                params={"llm": llm or llm_only, "docs": docs},
            ) as run:
                if not llm_only:
                    ics_count = await extract_events_workflow(session=session, dataset_id=resolved_id)
                    logger.success(f"Extracted events for {ics_count} calendar files")
                    run.units += ics_count
                if llm or llm_only:
                    groups = TEXT_EVENT_GROUPS_ALL if docs else TEXT_EVENT_GROUPS_EMAIL
                    text_count = await extract_text_events_workflow(
                        session=session, dataset_id=resolved_id, model=model, filetype_groups=groups
                    )
                    logger.success(f"Extracted events for {text_count} text files (llm)")
                    run.units += text_count

    asyncio.run(_run())


@app.command("extract-llm")
def extract_llm_cmd(
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
    tasks: Annotated[str, typer.Option(help="Comma list of sections to extract: entities, events")] = "entities,events",
    docs: Annotated[bool, typer.Option(help="Also scan document files (PDF/DOCX), not just email")] = False,
    model: Annotated[str | None, typer.Option(help="Override the configured LLM model id")] = None,
    limit: Annotated[
        int | None, typer.Option(help="Cap files processed this run (for A/B slices); rest stay pending")
    ] = None,
    concurrency: Annotated[
        int, typer.Option(help="LLM calls in flight at once, so the server can batch them")
    ] = DEFAULT_CONCURRENCY,
    max_files: Annotated[
        int, typer.Option(help="Refuse a run larger than this many files unless --yes")
    ] = DEFAULT_MAX_LLM_PASS_FILES,
    yes: Annotated[bool, typer.Option("--yes", help="Run the whole backlog even past --max-files")] = False,
):
    """Run entities/relations + events in ONE `pyprompt` call per file.

    One structured call over each email (and, with `--docs`, document) file
    produces `mention` / `mention_relationship` and `event` rows together, and
    completes both the ENTITY_EXTRACTION and EVENT_EXTRACTION enrichments. Halves
    the model calls versus `extract-entities --extractor llm` + `extract-events
    --llm`, and keeps the entity list and event participants consistent.

    `--tasks` selects the sections (`entities`, `events`, or both). For entity
    extraction over *all* file types, or the `nerd` / `gliner` engines, use
    `extract-entities`. Needs `pyprompt` and an `LLM__*` config.

    **This is slow.** LLM inference dominates; a bulk pass is an overnight job
    even with a fast served model and `--concurrency`. A run over more than
    `--max-files` (default 15,000) is refused unless `--yes` -- do a bounded
    `--limit` slice first, confirm the results, then run the rest. Prefer a
    standard ~7-30B instruct model (or a cloud model); tiny models like
    `gemma-3n-E2B` run ~20-40x slower under vLLM. Follow with `resolve-entities`
    then `resolve-event-links`.
    """
    ensure_stage_env("event-extraction")
    task_set = {t.strip().lower() for t in tasks.split(",") if t.strip()}

    async def _run():
        async with get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            groups = TEXT_EVENT_GROUPS_ALL if docs else TEXT_EVENT_GROUPS_EMAIL
            try:
                async with record_run(
                    enrichment_type=EnrichmentType.ENTITY_EXTRACTION,
                    dataset_id=resolved_id,
                    device="na",
                    unit=WorkUnit.LLM_FILE,
                    params={"tasks": sorted(task_set), "concurrency": concurrency, "docs": docs},
                ) as run:
                    run.units = await extract_llm_workflow(
                        session=session,
                        dataset_id=resolved_id,
                        tasks=task_set,
                        filetype_groups=groups,
                        model=model,
                        limit=limit,
                        concurrency=concurrency,
                        max_files=max_files,
                        yes=yes,
                    )
            except LlmPassTooLargeError as exc:
                raise typer.BadParameter(str(exc)) from exc
            logger.success(f"Combined LLM pass over {run.units} files")

    asyncio.run(_run())


@app.command("extract-entities")
def extract_entities_cmd(
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
    extractor: Annotated[str, typer.Option(help="Engine: llm | gliner | nerd")] = "llm",
    model: Annotated[str | None, typer.Option(help="Override the configured LLM model id (llm extractor)")] = None,
    gliner_model_dir: Annotated[
        str | None, typer.Option(help="Local GLiNER2.5 checkpoint dir (gliner extractor)")
    ] = None,
    nerd_model_dir: Annotated[
        str | None, typer.Option(help="Token-classification checkpoint dir (nerd extractor)")
    ] = None,
    threshold: Annotated[
        float | None, typer.Option(help="Span score floor. Default: 0.65 for gliner, 0.5 for nerd")
    ] = None,
    no_relations: Annotated[bool, typer.Option(help="Do not persist mention relations")] = False,
    device: Annotated[ModelDevice, typer.Option(help="Inference device (gliner / nerd)")] = ModelDevice.CPU,
    batch_size: Annotated[
        int, typer.Option(help="Files per batch; nerd packs a whole batch into shared GPU passes")
    ] = 25,
):
    """Run NER + relation extraction over a dataset's extracted text.

    Writes unresolved `person` / `organization` / `location` `mention` rows that
    `resolve-entities` promotes to entities, plus `mention_relationship` rows for
    every relation the extractor reports between two of those spans (promoted to
    the relationship review queue once both endpoints resolve). Selector-kind
    labels are left to `extract-selectors`. Re-run after `reset-entities`.

    Engines (all in-process): `llm` needs `pyprompt` + an `LLM__*` config;
    `gliner` needs `--gliner-model-dir` (entities + relations in one joint pass);
    `nerd` needs `--nerd-model-dir` (entities only).
    """
    if extractor in ("gliner", "nerd"):
        ensure_stage_env(extractor)

    async def _run():
        async with get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            async with record_run(
                enrichment_type=EnrichmentType.ENTITY_EXTRACTION,
                dataset_id=resolved_id,
                device="na",
                unit=WorkUnit.LLM_FILE if extractor == "llm" else WorkUnit.TEXT_FILE,
                params={"extractor": extractor},
            ) as run:
                run.units = await extract_entities_workflow(
                    session=session,
                    dataset_id=resolved_id,
                    extractor=extractor,
                    model=model,
                    gliner_model_dir=gliner_model_dir,
                    nerd_model_dir=nerd_model_dir,
                    threshold=threshold,
                    persist_relations=not no_relations,
                    device=device,
                    batch_size=batch_size,
                )
            logger.success(f"Extracted entity mentions for {run.units} files")

    asyncio.run(_run())


@app.command("resolve-entities")
def resolve_entities_cmd(
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
    min_mentions: Annotated[
        int, typer.Option(help="Provisional entity floor: create one only for an unmatched typed group this large")
    ] = 2,
    no_create: Annotated[bool, typer.Option(help="Never create provisional entities; attach to existing only")] = False,
    skip_selector_links: Annotated[
        bool, typer.Option(help="Skip upserting person->selector has_selector edges from headers")
    ] = False,
    auto_threshold: Annotated[float, typer.Option(help="Score at/above which a match auto-resolves")] = 0.92,
    review_low: Annotated[float, typer.Option(help="Score floor for surfacing a candidate in the review queue")] = 0.55,
    min_margin: Annotated[float, typer.Option(help="Required score gap over the runner-up to auto-resolve")] = 0.15,
    allow_auto_name: Annotated[
        bool, typer.Option(help="Also allow an exact-name match (no selector) to auto-resolve")
    ] = False,
    cross_dataset: Annotated[
        bool, typer.Option(help="Also match against other datasets' entities (review-only; never auto)")
    ] = False,
    concurrency: Annotated[
        int,
        typer.Option(help="Score this many name groups in parallel (own session each); ~Nx faster on a big mailbox"),
    ] = 8,
):
    """Sweep unresolved name mentions -> entities: block -> score -> decide -> emit.

    A dataset-wide pass. For each unresolved `name` group it blocks candidates
    (`entity_name_key` + selector + trigram), scores them (Fellegi-Sunter), then:
    auto-attaches the whole group on the one safe rule (exact selector on a
    structured header), files a pending group-level `entity_match` per candidate
    for the review queue, or -- if nothing clears `--review-low` -- promotes a
    trustworthy typed group to a provisional entity, else leaves it for Review.
    Idempotent; `reset-entities` clears everything it writes.
    """

    async def _run():
        async with get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            config = EntityResolutionConfig(
                auto_threshold=auto_threshold,
                review_low=review_low,
                min_margin=min_margin,
                auto_methods=["selector", "name_exact"] if allow_auto_name else ["selector"],
                create_provisional=not no_create,
                min_mentions=min_mentions,
                cross_dataset=cross_dataset,
            )
            counts = await resolve_entities_workflow(
                session=session,
                dataset_id=resolved_id,
                config=config,
                link_selectors=not skip_selector_links,
                concurrency=concurrency,
            )
            typer.echo(json.dumps(counts, indent=2))

    asyncio.run(_run())


@app.command("dedupe-entities")
def dedupe_entities_cmd(
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
    review_low: Annotated[float, typer.Option(help="Score floor for proposing a merge")] = 0.55,
):
    """Score every provisional entity against canonical entities and file merge proposals.

    `resolve-entities` mints a provisional entity when a trustworthy name group
    has no canonical match; nothing then re-checks that stub. This pass blocks
    canonical candidates for each stub, scores them with the same Fellegi-Sunter
    scorer, and writes a pending `entity_match` (with `provisional_entity_id`
    set) per candidate over `--review-low`. Never auto -- a merge is reviewed in
    the app; confirming runs `merge_entities`. Skips a pair an analyst already
    rejected. Idempotent.
    """

    async def _run():
        async with get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            config = EntityResolutionConfig(review_low=review_low)
            counts = await dedupe_entities_workflow(session=session, dataset_id=resolved_id, config=config)
            typer.echo(json.dumps(counts, indent=2))

    asyncio.run(_run())


@app.command("extract-contact-entities")
def extract_contact_entities_cmd(
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
):
    """Parse a dataset's vCard files into `contact` rows, then turn contacts into resolver-ready mentions.

    Each contact emits a person `name` mention plus its email/phone `selector`
    mentions under one shared `field_path`, so `resolve-entities` links the name
    to the identifier exactly as it does an email header. A `Contact.organization`
    also emits an org name mention + a `member_of` relation. Re-runnable.
    """
    ensure_stage_env("contact-extraction")

    async def _run():
        async with get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            async with record_run(
                enrichment_type=EnrichmentType.CONTACT_EXTRACTION,
                dataset_id=resolved_id,
                device="na",
                unit=WorkUnit.CONTACT_FILE,
            ) as run:
                counts = await extract_contact_entities_workflow(session=session, dataset_id=resolved_id)
                run.units = counts.get("contacts", 0)
            typer.echo(json.dumps(counts, indent=2))

    asyncio.run(_run())


@app.command("resolve-event-links")
def resolve_event_links_cmd(
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
):
    """Sweep unresolved event participant/place links -> `entity` / `location`.

    The event-layer counterpart to `resolve-entities`: matches an
    `event_participant` by its calendar email (`mailto:` -> the owning selector's
    person/org) then by normalized name against an existing person/organization,
    and an `event_place` by normalized name against an existing location. Rooms /
    resources are skipped and nothing is created -- unmatched links stay as
    `raw_name` / `raw_text`. Re-runnable; run after `extract-events` +
    `resolve-entities`.
    """

    async def _run():
        async with get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            counts = await resolve_event_links_workflow(session=session, dataset_id=resolved_id)
            typer.echo(json.dumps(counts, indent=2))

    asyncio.run(_run())


@app.command("backfill-entity-name-keys")
def backfill_entity_name_keys_cmd(
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
    batch_size: Annotated[int, typer.Option(help="Entities per keyset-paginated batch")] = 1000,
    purge: Annotated[
        bool, typer.Option(help="Delete every key row first (only with no dataset scope; for a KEYS_VERSION rebuild)")
    ] = False,
):
    """Populate / rebuild the `entity_name_key` blocking index for entity resolution.

    Recomputes `cipher.names.entity_keys` (transliterated / phonetic / sorted-token
    / surname / given+surname forms) for every person / organization / location
    entity and replaces its rows. Idempotent -- delete-then-insert per entity, so
    re-running heals drift. Only needed for initial adoption and after a
    `cipher-names` upgrade; inline refresh keeps the index current thereafter.
    Runs across all datasets when none is given.
    """

    async def _run():
        async with get_session_context() as session:
            resolved_id = None
            if dataset_name or dataset_id:
                resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            counts = await backfill_entity_name_keys_workflow(
                session=session, dataset_id=resolved_id, batch_size=batch_size, purge=purge
            )
            typer.echo(json.dumps(counts, indent=2))

    asyncio.run(_run())


@app.command("refresh-selectors")
def refresh_selectors_cmd(
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
):
    """Recompute normalization / validation / attributes on existing `selector` rows.

    Retroactive backfill against the current `pyselectors` packs and validators:
    refreshes `attributes` and `region_hint` on every selector row (all datasets
    if none is given). `normalized_value` is left untouched; rows that no longer
    validate are logged, not deleted.
    """

    async def _run():
        async with get_session_context() as session:
            resolved_id = None
            if dataset_name or dataset_id:
                resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            summary = await refresh_selectors_workflow(session=session, dataset_id=resolved_id)
            typer.echo(json.dumps(summary, indent=2))

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
    from cipher.schemas.ingestion.enrichment import EnrichmentType
    from cipher.utils.retrieval import RetrievalBackend, load_retrieval_config

    async def _run():
        cfg = load_retrieval_config()
        async with _text_chunk_es_repo() as es_repo, get_session_context() as session:
            if cfg.backend == RetrievalBackend.POSTGRES:
                from cipher.datastores.postgres.repositories.chunk_retrieval import (
                    PostgresChunkRetrievalRepository,
                )

                chunk_store = PostgresChunkRetrievalRepository(session=session, text_ranker=cfg.text_ranker.value)
            else:
                from cipher.datastores.elasticsearch.repositories.chunk_retrieval import (
                    ElasticsearchChunkRetrievalRepository,
                )

                chunk_store = ElasticsearchChunkRetrievalRepository(client=es_repo.client, session=session)

            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            deleted_chunks = await chunk_store.delete_by_dataset_id(resolved_id)

            enrichment_repo = PostgresEnrichmentRepository(session=session)
            reset_extraction = await enrichment_repo.delete_by_type(resolved_id, EnrichmentType.TEXT_EXTRACTION)
            # re-extraction overwrites the OCR-merged text, so OCR must run again too
            reset_extraction += await enrichment_repo.delete_by_type(resolved_id, EnrichmentType.OCR)
            reset_embedding = await enrichment_repo.delete_by_type(resolved_id, EnrichmentType.TEXT_EMBEDDING)

            logger.success(
                f"Reset dataset {resolved_id}: deleted {deleted_chunks} indexed chunks, "
                f"{reset_extraction} extraction + {reset_embedding} embedding enrichments cleared -- "
                "re-run extract-text, ocr, then embed-text to reprocess"
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

            staging = await PostgresDatasetRepository(session=session).get_staging_summary(resolved_id)
            typer.echo(
                f"Staged: {staging.is_staged}"
                + (f" (at {staging.date_staged:%Y-%m-%d %H:%M})" if staging.date_staged else "")
            )

            inventory = await PostgresFileRepository(session=session).get_dataset_inventory(resolved_id)
            typer.echo("Files by type:")
            for group, info in inventory.items():
                typer.echo(f"  {group}: {info['count']} files ({info['size_bytes']} bytes)")

            embedding_stats = await get_embedding_stats(session=session, dataset_id=resolved_id)
            typer.echo("Image embedding:")
            typer.echo(f"  {dict(embedding_stats.get(EnrichmentType.IMAGE_EMBEDDING, {}))}")

            from cipher.orchestration.detect_faces import get_face_detection_stats

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

            entity_stats = await get_entity_extraction_stats(session=session, dataset_id=resolved_id)
            typer.echo("Entity extraction (llm):")
            typer.echo(f"  {dict(entity_stats.get(EnrichmentType.ENTITY_EXTRACTION, {}))}")

            event_stats = await get_event_extraction_stats(session=session, dataset_id=resolved_id)
            typer.echo("Event extraction:")
            typer.echo(f"  {dict(event_stats.get(EnrichmentType.EVENT_EXTRACTION, {}))}")

    asyncio.run(_run())


@app.command("estimate")
def estimate_cmd(
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
    device: Annotated[
        str,
        typer.Option(
            help="Device for analytics that take --device (text/image embedding, face detection): cpu | cuda | mps"
        ),
    ] = "cpu",
):
    """Rough wall-time estimate per enrichment for a staged dataset.

    Uses the file inventory plus measured throughput from prior `enrichment_run`
    rows on the same device (a seeded default until enough real runs exist).
    Same numbers the request wizard shows.
    """
    from cipher.datastores.postgres.repositories import (
        PostgresEnrichmentRepository,
        PostgresEnrichmentRunRepository,
        PostgresFileRepository,
    )
    from cipher.schemas.ingestion.estimation import (
        ESTIMATE_ORDER,
        RunDevice,
        estimate_enrichment,
        estimate_workload,
        format_duration,
        resolve_rate,
        run_device,
        total_estimate_seconds,
    )

    async def _run():
        async with get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            accelerator = RunDevice(device)

            staging = await PostgresDatasetRepository(session=session).get_staging_summary(resolved_id)
            if not staging.is_staged:
                typer.echo("Dataset is not staged yet -- run load-files first.")
                return

            inventory = await PostgresFileRepository(session=session).get_dataset_inventory(resolved_id)
            rates = await PostgresEnrichmentRunRepository(session=session).get_rates()
            enr_repo = PostgresEnrichmentRepository(session=session)

            estimates = []
            for enrichment_type in ESTIMATE_ORDER:
                workload = estimate_workload(enrichment_type=enrichment_type, inventory=inventory)
                rate = resolve_rate(
                    enrichment_type=enrichment_type,
                    device=run_device(enrichment_type, accelerator=accelerator),
                    measured=rates,
                )
                stats = await enr_repo.get_enrichment_stats(dataset_id=resolved_id, enrichment_type=enrichment_type)
                counts = stats.get(enrichment_type, {})
                done = sum(counts.values())
                progress = (counts.get("completed", 0) / done) if done else 0.0
                estimates.append(estimate_enrichment(workload=workload, rate=rate, progress=progress))

            width = max(len(e.enrichment_type.value) for e in estimates)
            for e in estimates:
                eta = format_duration(e.estimate_seconds) if e.estimate_seconds is not None else "n/a"
                units = f"{e.eligible.unit_count} {e.eligible.unit.value}" if e.eligible.estimable else "-"
                typer.echo(
                    f"  {e.enrichment_type.value:<{width}}  {eta:>9}  [{e.confidence.value:<8}] {units:<18} {e.basis}"
                )
            typer.echo(f"\n  {'TOTAL (sequential)':<{width}}  {format_duration(total_estimate_seconds(estimates)):>9}")

    asyncio.run(_run())


@app.command("rates")
def rates_cmd(limit: Annotated[int, typer.Option(help="Recent runs to list")] = 20):
    """Show measured enrichment throughput (median seconds/unit) and recent runs."""
    from cipher.datastores.postgres.repositories import PostgresEnrichmentRunRepository

    async def _run():
        async with get_session_context() as session:
            repo = PostgresEnrichmentRunRepository(session=session)
            rates = await repo.get_rates()
            typer.echo("Measured rates (enrichment_type / device -> p50 s/unit, n):")
            if not rates:
                typer.echo("  (none yet)")
            for (etype, device), stat in sorted(rates.items(), key=lambda kv: kv[0][0].value):
                typer.echo(
                    f"  {etype.value:<24} {device.value:<5} {stat.seconds_per_unit:>8.3f}  "
                    f"(p25 {stat.low_per_unit:.3f} / p75 {stat.high_per_unit:.3f}, n={stat.sample_size})"
                )
            typer.echo(f"\nRecent runs (newest first, up to {limit}):")
            for row in await repo.list_recent(limit=limit):
                dur = f"{row.duration_seconds:.1f}s" if row.duration_seconds is not None else "-"
                typer.echo(
                    f"  {row.date_started:%Y-%m-%d %H:%M}  {row.enrichment_type:<22} {row.device:<5} "
                    f"{row.status:<10} {row.unit_count:>6} {row.unit:<12} {dur}"
                )

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
