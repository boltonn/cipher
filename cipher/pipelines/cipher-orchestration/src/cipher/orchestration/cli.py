"""Simple CLI for test-driving the ingestion + embedding + face-detection pipeline.

Deliberately minimal, and safe to run in any order or run twice: loading is
upsert-based (re-running on the same path is a no-op), and both the
embedding and face-detection commands dedupe by content hash before doing
any real work, so the same photo ingested more than once is only ever
embedded/detected once.
"""

import asyncio
import json
import os
from collections import Counter
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
from loguru import logger

from cipher.datastores.postgres.repositories import (
    PostgresDatasetRepository,
    PostgresEnrichmentRepository,
    PostgresFaceRepository,
    PostgresGraphRepository,
)
from cipher.orchestration.benchmark import benchmark_ingest, benchmark_storage
from cipher.orchestration.cluster_faces import cluster_faces_workflow, reset_face_clusters
from cipher.orchestration.embed_images import embed_images_workflow, get_embedding_stats
from cipher.orchestration.embed_text import DEFAULT_SKIP_EMAIL_STATES, embed_text_workflow, get_text_embedding_stats
from cipher.orchestration.environments import ensure_stage_env
from cipher.orchestration.extract_archives import (
    DEFAULT_MAX_DEPTH,
    GIB,
    extract_archives_workflow,
    missing_dependencies,
)
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
    DEFAULT_GATE_SAMPLE_RATE,
    DEFAULT_GATE_SKIP_CATEGORIES,
    DEFAULT_GATE_SKIP_STATES,
    DEFAULT_GATE_THRESHOLD,
    EVENT_GATE_LABELS,
    TEXT_EVENT_GROUPS_ALL,
    TEXT_EVENT_GROUPS_EMAIL,
    event_gate_score,
    extract_events_workflow,
    extract_text_events_workflow,
    gate_text_events_workflow,
    get_event_extraction_stats,
    get_event_gate_report,
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
from cipher.orchestration.extract_signatures import extract_signatures_workflow
from cipher.orchestration.ingest import create_dataset, load_files
from cipher.orchestration.link_face_cooccurrence import (
    get_face_cooccurrence_stats,
    link_face_cooccurrence_workflow,
)
from cipher.orchestration.match_faces import match_faces_workflow, reset_face_matches
from cipher.orchestration.rekey import REKEY_OPT_IN_PARTS, REKEY_PARTS, rekey_workflow
from cipher.orchestration.reset_entities import reset_entities
from cipher.orchestration.reset_events import reset_events
from cipher.orchestration.resolution import resolution_workflow
from cipher.orchestration.resolve_event_links import resolve_event_links_workflow
from cipher.orchestration.resolve_locations import resolve_locations_workflow
from cipher.orchestration.run_recorder import GPU_ENV, RunStoppedError, progress_writer, record_run
from cipher.orchestration.schema import create_tables, stamp_head
from cipher.orchestration.session import get_elasticsearch_client_context, get_session_context
from cipher.orchestration.settings import output_store, settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
from cipher.schemas._base.common import ModelDevice
from cipher.schemas.content.email import EmailCategory, MessageState
from cipher.schemas.content.extraction import OcrEngine
from cipher.schemas.graph.entity_resolution import EntityResolutionConfig
from cipher.schemas.identity.face import DEFAULT_FACE_SIMILARITY
from cipher.schemas.ingestion.enrichment import DEFAULT_FILETYPE_GROUPS, EnrichmentType
from cipher.schemas.ingestion.estimation import WorkUnit
from cipher.schemas.ingestion.file import ArchiveSandbox
from cipher.schemas.ingestion.run_plan import STAGING_RUN, StepPool

OUTPUT_URI_HELP = "Directory or s3://bucket/prefix for files this step creates (default <OUTPUT_URI>/<dataset id>)"

app = typer.Typer(help="Test-drive ingestion, embedding, and face detection against a local dataset.")


@asynccontextmanager
async def _text_chunk_es_repo():
    """The ES `text_chunks` repo when `RETRIEVAL__BACKEND=elasticsearch`, else None (ES never opened)."""
    from cipher.utils.retrieval import RetrievalBackend

    if settings.retrieval.backend == RetrievalBackend.POSTGRES:
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


def _required[T](value: T | None, *, option: str, env: str) -> T:
    """A required option whose default comes from settings: error when neither the flag nor `.env` gives it."""
    if value is None:
        raise typer.BadParameter(f"pass {option} or set {env} in .env")
    return value


def _run_llm_pass(coroutine) -> None:
    """Run an LLM pass; a stopped one (recorded `stopped`, its batch requeued) exits non-zero without a traceback."""
    try:
        asyncio.run(coroutine)
    except RunStoppedError as exc:
        logger.error(str(exc))
        raise typer.Exit(code=1) from exc


MinImageSideOption = Annotated[
    int,
    typer.Option(
        help="Skip images whose shorter side is under this many pixels (spacers, tracking pixels)",
    ),
]


@app.command("create-tables")
def create_tables_cmd(
    stamp_head_: Annotated[
        bool,
        typer.Option("--stamp-head", help="Mark an empty database just built here as at the latest migration"),
    ] = False,
):
    """Create all Postgres tables (idempotent; safe to run every time)."""

    async def _run():
        async with get_session_context() as session:
            await create_tables(session=session)
            logger.success("Tables ready")

    asyncio.run(_run())
    if stamp_head_:
        stamp_head()
        logger.success("Stamped at the latest migration")


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
    uri: Annotated[str, typer.Argument(help="Directory or s3://bucket/prefix/ to stage from (read-only)")],
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
    include: Annotated[
        list[str] | None, typer.Option(help="Glob a file's path below the uri must match, repeatable (any)")
    ] = None,
    exclude: Annotated[list[str] | None, typer.Option(help="Glob that drops a file, repeatable")] = None,
    limit: Annotated[int | None, typer.Option(help="Stop after this many files")] = None,
):
    """Stage files into a dataset: crawl the uri, type and hash each file, write `file` rows. No analysis.

    Nothing is copied: each row's uri points where the file already is. Files already staged
    are skipped, so an interrupted crawl resumes.
    """
    ensure_stage_env("staging")
    from filetyper.models.main import FileTyper

    async def _run():
        file_typer = FileTyper()
        async with get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            async with record_run(
                enrichment_type=STAGING_RUN,
                dataset_id=resolved_id,
                unit=WorkUnit.FILE,
                params={"uri": uri, "include": include or [], "exclude": exclude or [], "limit": limit},
            ) as run:
                run.units = await load_files(
                    session,
                    uri,
                    dataset_id=resolved_id,
                    file_typer=file_typer,
                    include=include or [],
                    exclude=exclude or [],
                    limit=limit,
                    on_progress=progress_writer(run.run_id),
                )

    asyncio.run(_run())


@app.command("worker")
def worker_cmd(
    pool: Annotated[StepPool, typer.Option(help="Kind of host this is: cpu, or gpu (one step per GPU)")],
    slots: Annotated[int, typer.Option(help="Steps run at once on a cpu worker")] = 1,
    gpu: Annotated[
        list[str] | None, typer.Option(help="GPU index a gpu worker may use, repeatable (default: all visible)")
    ] = None,
    llm_cap: Annotated[int, typer.Option(help="Most LLM steps running at once, across all workers")] = 1,
    max_hosts_per_step: Annotated[int, typer.Option(help="Most hosts sharing one per-file step")] = 4,
    strict_version: Annotated[
        bool, typer.Option(help="Refuse steps approved on another commit (default: run them and warn)")
    ] = False,
    poll_seconds: Annotated[float, typer.Option(help="How often to look for queued steps")] = 10,
    log_dir: Annotated[Path, typer.Option(help="One log file per step")] = Path("~/data/cipher/worker-logs"),
):
    """Run approved plan steps from the database on this host until stopped (Ctrl-C drains, twice interrupts).

    See docs/pipeline-runner.md. Needs only outbound access to Postgres (and S3 / the LLM service).
    """
    from cipher.orchestration.worker import Worker

    gpus = gpu or []
    if pool is StepPool.GPU and not gpus:
        import torch

        gpus = [str(index) for index in range(torch.cuda.device_count())]
        if not gpus:
            typer.echo("ERROR: no GPU visible; pass --gpu or run --pool cpu", err=True)
            raise typer.Exit(1)
    worker = Worker(
        pool=pool,
        slots=slots,
        gpus=gpus,
        caps={"llm": llm_cap},
        max_hosts_per_step=max_hosts_per_step,
        is_strict_version=strict_version,
        poll_seconds=poll_seconds,
        log_dir=log_dir.expanduser(),
    )
    asyncio.run(worker.run())


@app.command("runs")
def runs_cmd(
    here: Annotated[bool, typer.Option(help="Only steps running on this host")] = False,
):
    """Plan steps queued or running right now: where each runs, its pids and its log file.

    On the host, `tail -f <log>` follows a step, `ps -g <pid>` shows its processes, and a step
    is stopped from the app (or Ctrl-C on its worker).
    """
    import socket
    from datetime import UTC, datetime

    from cipher.datastores.postgres.repositories import PostgresEnrichmentRunRepository

    async def _run():
        async with get_session_context() as session:
            steps = await PostgresEnrichmentRunRepository(session=session).live_steps(
                host=socket.gethostname() if here else None
            )
            names = {
                dataset_id: (await PostgresDatasetRepository(session=session).get_dataset_by_id(dataset_id=dataset_id))
                for dataset_id in {step.dataset_id for step in steps}
            }
        if not steps:
            typer.echo("Nothing queued or running" + (" on this host." if here else "."))
            return
        now = datetime.now(UTC)
        for step in sorted(steps, key=lambda step: step.status == "queued"):
            dataset = names.get(step.dataset_id)
            process = step.process or {}
            heard = f"{int((now - step.date_heartbeat).total_seconds())}s ago" if step.date_heartbeat else "-"
            typer.echo(
                f"{step.status:<10} {step.enrichment_type:<24} {dataset.name if dataset else step.dataset_id}\n"
                + (
                    f"           host {process.get('host')}  worker pid {process.get('worker_pid')}  "
                    f"step pid {process.get('pid')}  last heard {heard}\n           log  {process.get('log')}\n"
                    if process and step.status != "queued"
                    else f"           waiting for {', '.join(step.depends_on) or 'a ' + (step.pool or 'cpu') + ' worker'}\n"
                )
            )

    asyncio.run(_run())


@app.command("embed-images")
def embed_images_cmd(
    model_dir: Annotated[
        Path | None, typer.Option(help="Path to the CLIP model directory")
    ] = settings.image_embedding_model_dir,
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
    device: Annotated[ModelDevice, typer.Option(help="Inference device")] = settings.image_embedding_model_device,
    classify: Annotated[
        bool, typer.Option(help="Also score every image with the tag heads, in the same GPU pass")
    ] = False,
    heads_dir: Annotated[
        Path | None, typer.Option(help="Trained tag heads (from train-image-heads)")
    ] = settings.image_heads_dir,
    min_image_side: MinImageSideOption = settings.min_image_side,
):
    """Run CLIP image embedding over a dataset's image files.

    Independent of `detect-faces` -- either can run first. With `--classify`, the tag heads
    in `--heads-dir` score each batch as it is embedded (one extra matmul on the GPU).
    """
    model_dir = _required(model_dir, option="--model-dir", env="IMAGE_EMBEDDING_MODEL_DIR")
    ensure_stage_env("image-embedding")
    from setfitcv.heads import TagHeads
    from setfitcv.model import CLIP

    if classify and heads_dir is None:
        raise typer.BadParameter("--classify needs --heads-dir (or IMAGE_HEADS_DIR in .env)")
    heads = TagHeads.load(heads_dir) if classify else None

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
                run.units = await embed_images_workflow(
                    session=session, model=model, dataset_id=resolved_id, heads=heads, min_image_side=min_image_side
                )
            logger.success(f"Embedded {run.units} images")

    asyncio.run(_run())


@app.command("train-image-heads")
def train_image_heads_cmd(
    embedding_model: Annotated[
        str, typer.Option(help="CLIP model the stored embeddings came from (its directory name)")
    ],
    heads_dir: Annotated[Path | None, typer.Option(help="Where to save the trained heads")] = settings.image_heads_dir,
    tag: Annotated[list[str] | None, typer.Option(help="Tag to train, repeatable; default every labelled tag")] = None,
    min_positives: Annotated[int, typer.Option(help="Skip tags with fewer positive labels")] = 8,
    unlabeled_per_positive: Annotated[
        int, typer.Option(help="Random unlabelled images drawn as weak negatives, per positive")
    ] = 3,
    unlabeled_weight: Annotated[float, typer.Option(help="Sample weight of those weak negatives")] = 0.3,
):
    """Train one lightweight classifier per tag on the image embeddings already in Postgres.

    Positives are images labelled with the tag, hard negatives those labelled "not" it, plus
    down-weighted random unlabelled images. CPU-only (scikit-learn); writes `heads.safetensors`
    + `heads.json`, overwriting the previous bank. Run `score-image-heads` afterwards.
    """
    ensure_stage_env("image-heads")
    from setfitcv.train import TrainingConfig

    from cipher.orchestration.image_heads import train_image_heads_workflow

    heads_dir = _required(heads_dir, option="--heads-dir", env="IMAGE_HEADS_DIR")

    async def _run():
        async with get_session_context() as session:
            await train_image_heads_workflow(
                session,
                embedding_model=embedding_model,
                heads_dir=heads_dir,
                tags=tag or None,
                unlabeled_per_positive=unlabeled_per_positive,
                config=TrainingConfig(min_positives=min_positives, unlabeled_weight=unlabeled_weight),
            )

    asyncio.run(_run())


@app.command("score-image-heads")
def score_image_heads_cmd(
    heads_dir: Annotated[Path | None, typer.Option(help="Trained tag heads")] = settings.image_heads_dir,
    dataset_name: Annotated[str | None, typer.Option(help="Only this dataset's images")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Only this dataset's images")] = None,
    tag: Annotated[list[str] | None, typer.Option(help="Only these heads, repeatable")] = None,
    min_score: Annotated[float, typer.Option(help="Don't store scores below this")] = 0.2,
):
    """Score embedded images with the tag heads and store the results as model tag scores.

    Works from stored embeddings (CPU matmul, no images read). Replaces any earlier heads
    version's scores, so retrain -> rescore keeps exactly one current score per image and tag.
    Scores show up in the image grid's *Predicted* view for review.
    """
    ensure_stage_env("image-heads")
    from setfitcv.heads import TagHeads

    from cipher.orchestration.image_heads import score_image_heads_workflow

    heads = TagHeads.load(_required(heads_dir, option="--heads-dir", env="IMAGE_HEADS_DIR"))
    if tag:
        heads = heads.select(tag)

    async def _run():
        async with get_session_context() as session:
            resolved_id = (
                await _resolve_dataset_id(session, dataset_id, dataset_name) if dataset_id or dataset_name else None
            )
            count = await score_image_heads_workflow(session, heads=heads, dataset_id=resolved_id, min_score=min_score)
            logger.success(f"Scored {count} images with {len(heads.tags)} heads ({heads.version})")

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
    model_dir: Annotated[
        Path | None, typer.Option(help="Path to the InsightFace model directory")
    ] = settings.face_model_dir,
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
    device: Annotated[ModelDevice, typer.Option(help="Inference device")] = settings.face_model_device,
    min_image_side: MinImageSideOption = settings.min_image_side,
):
    """Run face detection over a dataset's image files."""
    model_dir = _required(model_dir, option="--model-dir", env="FACE_MODEL_DIR")
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
                run.units = await detect_faces_workflow(
                    session=session, model=model, dataset_id=resolved_id, min_image_side=min_image_side
                )
            logger.success(f"Face detection processed {run.units} files")

    asyncio.run(_run())


async def _unpack(
    session: "AsyncSession",
    dataset_id: str,
    *,
    output_uri: str | None = None,
    max_depth: int = DEFAULT_MAX_DEPTH,
    limits: dict[str, float | str] | None = None,
    passwords_file: Path = settings.archive_passwords_file,
) -> Counter:
    """Archive extraction as its own recorded run (shared by extract-archives and extract-text)."""
    from pyarchive import ArchiveLimits

    async with record_run(
        enrichment_type=EnrichmentType.ARCHIVE_EXTRACTION,
        dataset_id=dataset_id,
        unit=WorkUnit.FILE,
        params={"max_depth": max_depth, **(limits or {})},
    ) as run:
        counts = await extract_archives_workflow(
            session,
            dataset_id,
            output_store(dataset_id=dataset_id, output_uri=output_uri),
            ArchiveLimits(**(limits or {})),
            max_depth=max_depth,
            run_id=run.run_id,
            passwords_file=passwords_file,
        )
        run.units = sum(n for key, n in counts.items() if key == "completed" or key.startswith(("skipped:", "failed:")))
    return counts


async def _exit_if_tools_missing(session: "AsyncSession", dataset_id: str) -> None:
    """Exit 1 naming what to install when archives couldn't be unpacked for a missing tool (retried next run)."""
    if missing := await missing_dependencies(session, dataset_id):
        for need, archives in missing.items():
            typer.echo(f"ERROR: {archives:,} archive(s) not unpacked: {need}", err=True)
        typer.echo("They are retried on the next run once it's installed.", err=True)
        raise typer.Exit(1)


@app.command("extract-archives")
def extract_archives_cmd(
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
    output_uri: Annotated[str | None, typer.Option(help=OUTPUT_URI_HELP)] = None,
    max_archive_gib: Annotated[
        float | None,
        typer.Option(
            help="Skip archives bigger than this (PYARCHIVE_MAX_ARCHIVE_GIB; default none for local files, "
            "50 for S3, where 7z/rar/iso must be copied first)"
        ),
    ] = None,
    max_depth: Annotated[int, typer.Option(help="Most archives-within-archives levels to open")] = DEFAULT_MAX_DEPTH,
    max_total_gib: Annotated[float, typer.Option(help="Most GiB one archive may write")] = 20,
    max_member_gib: Annotated[float, typer.Option(help="Most GiB one member may write")] = 8,
    max_ratio: Annotated[
        float, typer.Option(help="Most bytes written per compressed byte, per member past 64 MiB (zip bombs)")
    ] = 250,
    max_entries: Annotated[int, typer.Option(help="Most members one archive may list")] = 1_000_000,
    min_free_gib: Annotated[float, typer.Option(help="Stop an archive when the output store disk has less free")] = 10,
    sandbox: Annotated[
        ArchiveSandbox,
        typer.Option(
            help="How 7zz is confined: best_effort (what this machine allows), required (fail those archives "
            "otherwise), off (where the sandbox gets in 7zz's way; check with `pyarchive sandbox`)"
        ),
    ] = ArchiveSandbox.BEST_EFFORT,
    passwords_file: Annotated[
        Path, typer.Option(help="Passwords to try on encrypted members, one per line (ARCHIVE_PASSWORDS_FILE)")
    ] = settings.archive_passwords_file,
):
    """Unpack archives into member files, and decode compressed files in place.

    zip and tar (also .tar.gz / .xz / .bz2 / .zst) -- and 7z, rar, iso, cab when 7zz is installed
    (SEVENZIP_PATH, PATH or ~/.local/share/cipher/bin/7zz; run sandboxed) -- become one file per
    member, `parent_id` the archive, bytes in the output store. Encrypted members are tried with
    each password in --passwords-file; archives holding encrypted members are flagged
    `is_encrypted` and, when that file changes, queued again for whatever is still missing. A file found compressed (report.csv.gz) is decoded into
    its row. Nested archives are opened pass by pass up to --max-depth; copies of content
    already unpacked, and archives that contain themselves, are skipped. Resumes where an
    interrupted run stopped. Run before every other file analytic (extract-text runs it too).
    """
    ensure_stage_env("archive-extraction")
    limits = {
        "max_archive_bytes": int(max_archive_gib * GIB) if max_archive_gib is not None else None,
        "max_total_bytes": int(max_total_gib * GIB),
        "max_member_bytes": int(max_member_gib * GIB),
        "max_ratio": max_ratio,
        "max_entries": max_entries,
        "min_free_bytes": int(min_free_gib * GIB),
        "sandbox": sandbox,
    }

    async def _run():
        async with get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            counts = await _unpack(
                session,
                resolved_id,
                output_uri=output_uri,
                max_depth=max_depth,
                limits=limits,
                passwords_file=passwords_file,
            )
            typer.echo(json.dumps(dict(counts), indent=2))
            await _exit_if_tools_missing(session, resolved_id)

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
    max_concurrent_extractions: Annotated[
        int | None,
        typer.Option(help="Cap xberg's internal batch parallelism -- default is xberg's own num_cpus*2"),
    ] = None,
    ocr_backend: Annotated[
        OcrBackend,
        typer.Option(
            help="Inline OCR for image-based PDF pages. Default none: they are recorded and `cipher ocr` reads them. "
            "easyocr is the fallback for a machine that can't run `cipher ocr`"
        ),
    ] = OcrBackend.NONE,
    ocr_language: Annotated[
        list[str] | None, typer.Option(help="OCR language code, repeatable (EasyOCR: en, fr...; Tesseract: eng...)")
    ] = None,
    ocr_model_dir: Annotated[
        Path | None,
        typer.Option(help="Pre-downloaded EasyOCR weights, so OCR never downloads"),
    ] = settings.easyocr_model_dir,
    filetype_group: Annotated[
        list[str] | None,
        typer.Option(
            help="Filetype group to process, repeatable (default: document, email). Add `table` to include spreadsheets"
        ),
    ] = None,
    archives: Annotated[
        bool,
        typer.Option(help="Unpack archives first, and again for any found in emails (extract-archives defaults)"),
    ] = True,
    inline_images: Annotated[
        bool,
        typer.Option(
            help="Save images email bodies show (cid: links) as files found in the email; never listed as attachments"
        ),
    ] = True,
    output_uri: Annotated[str | None, typer.Option(help=OUTPUT_URI_HELP)] = None,
):
    """Extract text (and structure) from a dataset's eligible files.

    Unpacks archives first (`extract-archives`, unless --no-archives), then loops emails and
    unpacking until neither finds anything new -- a zip can hold an email whose attachment is
    another zip -- and only then reads documents, so every member is in this pass.

    Runs emails first (pyparse) -- which also persists any attachments as
    their own files, linked via `parent_id` -- then documents (xberg,
    batched), so attachments discovered this run are swept up in the same
    pass. PDF pages without a usable text layer are recorded as
    `metadata.image_pages` and OCR'd inline (EasyOCR by default); re-run just
    those with a stronger model via `cipher ocr`.
    """
    ensure_stage_env("text-extraction", *(["archive-extraction"] if archives else []))
    ocr = XbergOcr(backend=ocr_backend, languages=ocr_language or ["en"], model_dir=ocr_model_dir)
    if ocr_backend == OcrBackend.EASYOCR and ocr_model_dir is None:
        logger.warning("No --ocr-model-dir / EASYOCR_MODEL_DIR -- EasyOCR will try to download its weights")

    groups = filetype_group or list(DEFAULT_FILETYPE_GROUPS[EnrichmentType.TEXT_EXTRACTION])

    async def _run():
        async with get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            async with record_run(
                enrichment_type=EnrichmentType.TEXT_EXTRACTION,
                dataset_id=resolved_id,
                device="na",
                unit=WorkUnit.TEXT_FILE,
                params={
                    "chunker": chunker.value,
                    "chunk_size": chunk_size,
                    "ocr_backend": ocr_backend.value,
                    "filetype_groups": groups,
                },
            ) as run:
                email_count = 0
                store = output_store(dataset_id=resolved_id, output_uri=output_uri)
                if archives:
                    await _unpack(session, resolved_id, output_uri=output_uri)
                while "email" in groups:
                    email_count += await extract_emails_workflow(
                        session=session, dataset_id=resolved_id, store=store, save_inline_images=inline_images
                    )
                    if not archives:
                        break
                    unpacked = await _unpack(session, resolved_id, output_uri=output_uri)
                    if not (unpacked["members"] or unpacked["decoded"]):
                        break
                logger.success(f"Extracted text for {email_count} emails")
                doc_count = await extract_documents_workflow(
                    session=session,
                    dataset_id=resolved_id,
                    chunker=chunker,
                    tokenizer_model_dir=model_dir,
                    chunk_size=chunk_size,
                    max_concurrent_extractions=max_concurrent_extractions,
                    ocr=ocr,
                    filetype_groups=groups,
                )
                logger.success(f"Extracted text for {doc_count} document files")
                run.units = email_count + doc_count
            if archives:
                await _exit_if_tools_missing(session, resolved_id)

    asyncio.run(_run())


@app.command("ocr")
def ocr_cmd(
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
    filetype: Annotated[
        list[str] | None,
        typer.Option(help="Filetype(s) to OCR, repeatable (e.g. pdf, heif). Default: every PDF + supported image"),
    ] = None,
    engine: Annotated[
        OcrEngine,
        typer.Option(
            help="jina: jina-ocr-v1 on the GPU (vLLM), best quality. "
            "indra: Indra OCR in this process on CPU, no server -- fast on clean print. See docs/running-analytics.md"
        ),
    ] = OcrEngine.JINA,
    service_url: Annotated[
        list[str] | None,
        typer.Option(
            help="jina only: OCR model URL, repeatable -- one per GPU. "
            "Default: pyvllm's `ocr` model on :8010, started for this run if it isn't already up"
        ),
    ] = None,
    workers: Annotated[
        int | None, typer.Option(help="indra only: CPU worker processes (default: every usable core)")
    ] = None,
    concurrency: Annotated[
        int, typer.Option(help="Files in flight across all services; each decodes its files' pages together")
    ] = 32,
    min_chars: Annotated[int, typer.Option(help="PDF pages with fewer text-layer word chars are OCR'd")] = 20,
    force: Annotated[bool, typer.Option(help="OCR every PDF page, not just image-based ones")] = False,
    figures: Annotated[bool, typer.Option(help="jina only: also locate + caption figures (grounding prompt)")] = False,
    clip_model_dir: Annotated[
        Path | None,
        typer.Option(
            help="CLIP model dir for the image text gate: only images matching --clip-tag are OCR'd (needs embed-images)",
        ),
    ] = settings.image_embedding_model_dir,
    all_images: Annotated[bool, typer.Option(help="Skip the text gate and OCR every image")] = False,
    clip_tag: Annotated[list[str] | None, typer.Option(help="Text-bearing CLIP tag, repeatable")] = None,
    clip_negative_tag: Annotated[list[str] | None, typer.Option(help="Competing non-text CLIP tag, repeatable")] = None,
    clip_threshold: Annotated[float, typer.Option(help="Min probability mass on --clip-tag to OCR an image")] = 0.5,
    min_image_side: MinImageSideOption = settings.min_image_side,
):
    """OCR image-based PDF pages and images into extracted text (run after extract-text).

    With `--engine jina` (default) the OCR model (pyvllm's `ocr`, jina-ocr-v1) runs locally on a GPU: one
    already serving is reused, otherwise it is started for this run and stopped afterwards. `--engine indra`
    reads pages with Indra OCR inside this process on CPU, no server. Images pass a text gate first --
    zero-shot CLIP tags scored against the embeddings `embed-images` already stored,
    kept as each file's `has_text` tag score -- so only likely text-bearing images
    (screenshots, scans, receipts, signs...) are sent to the model.
    """
    ensure_stage_env("ocr")
    from contextlib import AsyncExitStack

    from cipher.orchestration.ocr import (
        DEFAULT_CLIP_NEGATIVE_TAGS,
        DEFAULT_CLIP_TAGS,
        ClipTagFilter,
        get_ocr_stats,
        ocr_workflow,
    )

    clip_filter = None
    if all_images:
        logger.info("Text gate off: every image will be OCR'd")
    elif clip_model_dir is None:
        logger.warning("No CLIP model dir (IMAGE_EMBEDDING_MODEL_DIR) -- no text gate, every image will be OCR'd")
    else:
        from setfitcv.model import CLIP

        clip_filter = ClipTagFilter.from_model(
            model=CLIP(model_dir=clip_model_dir, device="cpu", warmup=False),
            model_name=f"clip:{Path(clip_model_dir).name}",
            tags=clip_tag or list(DEFAULT_CLIP_TAGS),
            negative_tags=clip_negative_tag or list(DEFAULT_CLIP_NEGATIVE_TAGS),
            threshold=clip_threshold,
        )

    async def _run():
        async with AsyncExitStack() as stack:
            if engine == OcrEngine.INDRA:
                from pyocr.indra import IndraOcr

                if figures:
                    logger.warning("--figures needs --engine jina; Indra OCR reads text only")
                client = IndraOcr(workers=workers)
            else:
                from pyocr.jina import JinaOcr
                from pyvllm.server import serving

                gpu = int(os.environ[GPU_ENV]) if GPU_ENV in os.environ else None  # set by `cipher worker`
                urls = service_url or [(await stack.enter_async_context(serving("ocr", gpu=gpu))).base_url]
                client = JinaOcr(base_urls=urls)
            stack.push_async_callback(client.aclose)
            async with get_session_context() as session:
                resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
                async with record_run(
                    enrichment_type=EnrichmentType.OCR,
                    dataset_id=resolved_id,
                    device="cpu" if engine == OcrEngine.INDRA else "cuda",
                    unit=WorkUnit.FILE,
                    params={
                        "engine": engine.value,
                        "filetypes": filetype,
                        "clip": clip_filter is not None,
                        "force": force,
                        "figures": figures,
                    },
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
                        min_image_side=min_image_side,
                    )
                logger.success(f"OCR stats: {await get_ocr_stats(session=session, dataset_id=resolved_id)}")

    asyncio.run(_run())


@app.command("embed-text")
def embed_text_cmd(
    model_dir: Annotated[
        Path | None, typer.Option(help="Path to the text embedding model directory")
    ] = settings.text_embedding_model_dir,
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
    device: Annotated[ModelDevice, typer.Option(help="Inference device")] = settings.text_embedding_model_device,
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
        list[MessageState] | None,
        typer.Option(
            help="Email states to exclude from embedding entirely (repeat the flag to skip several); default: spam"
        ),
    ] = None,
    filetype_group: Annotated[
        list[str] | None,
        typer.Option(
            help="Filetype group to process, repeatable (default: document, email, image). Add `table` to include spreadsheets"
        ),
    ] = None,
):
    """Chunk (if needed) and embed a dataset's extracted text into the chunk store (`RETRIEVAL__BACKEND`).

    Run `extract-text` first -- this reads persisted `ExtractedText` rows,
    it doesn't parse files itself. Elasticsearch is only opened when
    `RETRIEVAL__BACKEND=elasticsearch`.
    """
    model_dir = _required(model_dir, option="--model-dir", env="TEXT_EMBEDDING_MODEL_DIR")
    ensure_stage_env("text-embedding")
    from clir.models.pytorch import TextEmbeddingPytorchModel

    groups = filetype_group or list(DEFAULT_FILETYPE_GROUPS[EnrichmentType.TEXT_EMBEDDING])

    async def _run():
        model = TextEmbeddingPytorchModel(model_dir=model_dir, device=device.value)
        async with _text_chunk_es_repo() as es_repo, get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            async with record_run(
                enrichment_type=EnrichmentType.TEXT_EMBEDDING,
                dataset_id=resolved_id,
                device=device.value,
                unit=WorkUnit.TEXT_FILE,
                params={"chunk_size": chunk_size, "max_pages": max_pages, "filetype_groups": groups},
            ) as run:
                run.units = await embed_text_workflow(
                    filetype_groups=groups,
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
    filetype_group: Annotated[
        list[str] | None,
        typer.Option(
            help="Filetype group to process, repeatable (default: document, email, image). Add `table` to include spreadsheets"
        ),
    ] = None,
    rescan: Annotated[
        bool, typer.Option(help="Revisit already-processed files and add only the body spans they're missing")
    ] = False,
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
    groups = filetype_group or list(DEFAULT_FILETYPE_GROUPS[EnrichmentType.SELECTOR_EXTRACTION])

    async def _run():
        async with get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            async with record_run(
                enrichment_type=EnrichmentType.SELECTOR_EXTRACTION,
                dataset_id=resolved_id,
                device="na",
                unit=WorkUnit.TEXT_FILE,
            ) as run:
                run.units = await extract_selectors_workflow(
                    filetype_groups=groups, session=session, dataset_id=resolved_id, rescan=rescan
                )
            logger.success(f"Extracted selectors for {run.units} files")

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
                unit=WorkUnit.TEXT_FILE,
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
    similarity: Annotated[
        float, typer.Option(help="Min cosine similarity to propose a match")
    ] = DEFAULT_FACE_SIMILARITY,
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
                async with record_run(
                    enrichment_type=EnrichmentType.FACE_MATCHING,
                    dataset_id=resolved_id,
                    unit=WorkUnit.FACE,
                    params={"similarity": similarity, "verified_only": verified_only},
                ) as run:
                    counts = await match_faces_workflow(
                        session=session,
                        dataset_id=resolved_id,
                        min_similarity=similarity,
                        verified_only=verified_only,
                        per_face_limit=per_face_limit,
                        rebuild_cooccurrence=not no_cooccurrence,
                    )
                    run.units = counts.get("faces_touched", 0)
            typer.echo(json.dumps(counts, indent=2))

    asyncio.run(_run())


@app.command("reject-similar-faces")
def reject_similar_faces_cmd(
    similarity: Annotated[
        float, typer.Option(help="Min cosine similarity to a manually rejected face to auto-reject")
    ] = DEFAULT_FACE_SIMILARITY,
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
    similarity: Annotated[
        float, typer.Option(help="Min cosine similarity for a face-to-face cluster edge")
    ] = DEFAULT_FACE_SIMILARITY,
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
            async with record_run(
                enrichment_type=EnrichmentType.FACE_CLUSTERING,
                dataset_id=resolved_id,
                unit=WorkUnit.FACE,
                params={"similarity": similarity, "min_images": min_images, "min_faces": min_faces},
            ) as run:
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
                run.units = counts.get("faces_assigned", 0)
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
    concurrency: Annotated[int, typer.Option(help="LLM calls in flight at once")] = DEFAULT_CONCURRENCY,
    gate: Annotated[
        bool, typer.Option(help="Score every text with GLiNER first and send only likely events to the LLM")
    ] = True,
    gate_threshold: Annotated[
        float, typer.Option(help="Gate score a file needs to reach the LLM")
    ] = DEFAULT_GATE_THRESHOLD,
    gate_sample_rate: Annotated[
        float, typer.Option(help="Share of gate-rejected files the LLM still reads, to measure what the gate misses")
    ] = DEFAULT_GATE_SAMPLE_RATE,
    gate_skip_category: Annotated[
        list[EmailCategory] | None,
        typer.Option(help="Mail-client inbox category the gate skips (repeatable; default: promotions)"),
    ] = None,
    gate_skip_state: Annotated[
        list[MessageState] | None,
        typer.Option(help="Mail state the gate skips (repeatable; default: spam)"),
    ] = None,
    gliner_model_dir: Annotated[
        str | None, typer.Option(help="Local GLiNER2.5 checkpoint dir (gate)")
    ] = settings.gliner_model_dir,
    device: Annotated[ModelDevice, typer.Option(help="Gate inference device")] = settings.gliner_model_device,
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

    The LLM pass is gated by default: GLiNER scores each text for "a person is
    taking part in something" and only files at or above `--gate-threshold` are
    read, plus a `--gate-sample-rate` slice of the rest so the gate's misses can
    be measured (printed as a report at the end). Files the LLM reads are tagged
    `event` in `file.tags` / `file.negative_tags`. `--no-gate` reads everything.
    """
    use_gate = gate and (llm or llm_only)
    skip = {
        "skip_categories": frozenset(gate_skip_category or DEFAULT_GATE_SKIP_CATEGORIES),
        "skip_states": frozenset(gate_skip_state or DEFAULT_GATE_SKIP_STATES),
    }
    if use_gate and not gliner_model_dir:
        raise typer.BadParameter(
            "the gate needs --gliner-model-dir (or GLINER_MODEL_DIR in .env); pass --no-gate to skip it"
        )
    ensure_stage_env(*(("event-extraction", "gliner") if use_gate else ("event-extraction",)))

    async def _run():
        async with get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            async with record_run(
                enrichment_type=EnrichmentType.EVENT_EXTRACTION,
                dataset_id=resolved_id,
                device="na",
                # An LLM run's rate is per file the LLM reads; a calendar-only run's isn't comparable.
                unit=WorkUnit.LLM_FILE if llm or llm_only else WorkUnit.FILE,
                params={
                    "llm": llm or llm_only,
                    "docs": docs,
                    "gate": use_gate,
                    "gate_threshold": gate_threshold,
                    **{k: sorted(v) for k, v in skip.items()},
                },
            ) as run:
                if not llm_only:
                    ics_count = await extract_events_workflow(session=session, dataset_id=resolved_id)
                    logger.success(f"Extracted events for {ics_count} calendar files")
                    if not (llm or llm_only):
                        run.units += ics_count
                if llm or llm_only:
                    groups = TEXT_EVENT_GROUPS_ALL if docs else TEXT_EVENT_GROUPS_EMAIL
                    if use_gate:
                        from pygliner.model import GlinerModel

                        gliner = GlinerModel(gliner_model_dir, device=device)
                        await gate_text_events_workflow(
                            session=session,
                            dataset_id=resolved_id,
                            score_texts=lambda texts: [
                                event_gate_score(scores) for scores in gliner.classify(texts, EVENT_GATE_LABELS)
                            ],
                            threshold=gate_threshold,
                            sample_rate=gate_sample_rate,
                            **skip,
                            filetype_groups=groups,
                            model=f"gliner:{Path(gliner_model_dir).name}",
                        )
                        gliner.unload()
                    text_count = await extract_text_events_workflow(
                        session=session,
                        dataset_id=resolved_id,
                        model=model,
                        filetype_groups=groups,
                        concurrency=concurrency,
                    )
                    logger.success(f"Extracted events for {text_count} text files (llm)")
                    run.units += text_count
                    if use_gate:
                        report = await get_event_gate_report(session, resolved_id, threshold=gate_threshold, **skip)
                        typer.echo(json.dumps(report, indent=2))

    _run_llm_pass(_run())


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

    _run_llm_pass(_run())


@app.command("extract-entities")
def extract_entities_cmd(
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
    extractor: Annotated[str, typer.Option(help="Engine: nerd | gliner | llm")] = "nerd",
    model: Annotated[str | None, typer.Option(help="Override the configured LLM model id (llm extractor)")] = None,
    gliner_model_dir: Annotated[
        str | None, typer.Option(help="Local GLiNER2.5 checkpoint dir (gliner extractor)")
    ] = settings.gliner_model_dir,
    nerd_model_dir: Annotated[
        str | None, typer.Option(help="Token-classification checkpoint dir (nerd extractor)")
    ] = settings.nerd_model_dir,
    threshold: Annotated[
        float | None, typer.Option(help="Span score floor. Default: 0.65 for gliner, 0.5 for nerd")
    ] = None,
    no_relations: Annotated[bool, typer.Option(help="Do not persist mention relations")] = False,
    device: Annotated[
        ModelDevice | None,
        typer.Option(help="Inference device (gliner / nerd). Default: GLINER_MODEL_DEVICE / NERD_MODEL_DEVICE"),
    ] = None,
    batch_size: Annotated[
        int, typer.Option(help="Files per batch; nerd packs a whole batch into shared GPU passes")
    ] = 25,
    filetype_group: Annotated[
        list[str] | None,
        typer.Option(
            help="Filetype group to process, repeatable (default: document, email, image). Add `table` to include spreadsheets"
        ),
    ] = None,
    rescan: Annotated[
        bool,
        typer.Option(
            help="Re-extract already-processed files, keeping each name's resolved entity; hand-corrected texts are skipped"
        ),
    ] = False,
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
    if device is None:
        device = settings.nerd_model_device if extractor == "nerd" else settings.gliner_model_device

    groups = filetype_group or list(DEFAULT_FILETYPE_GROUPS[EnrichmentType.ENTITY_EXTRACTION])

    async def _run():
        async with get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            async with record_run(
                enrichment_type=EnrichmentType.ENTITY_EXTRACTION,
                dataset_id=resolved_id,
                device="na",
                unit=WorkUnit.LLM_FILE if extractor == "llm" else WorkUnit.TEXT_FILE,
                params={"extractor": extractor, "filetype_groups": groups},
            ) as run:
                run.units = await extract_entities_workflow(
                    filetype_groups=groups,
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
                    rescan=rescan,
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
    skip_locations: Annotated[
        bool, typer.Option(help="Skip the gazetteer pass over location mentions (see `resolve-locations`)")
    ] = False,
    full: Annotated[
        bool, typer.Option(help="Re-score every auto-created entity, not just those created since the last run")
    ] = False,
):
    """The whole entity-resolution stage, one call: match -> decide -> derive.

    One unit per name key (`normalize_name`: formatting, possessive, legal form and type
    aside -- `Adaire`, `Adaire's`, `Adaire (no reply)` are one unit):

    1. **Same names**: auto-created entities of one type fold into the unit's keeper; the
       unit's names attach to an auto-created keeper; same name / other type is asked.
    2. **Match names**: block candidates (`entity_name_key` + selector + trigram), score them
       (Fellegi-Sunter), attach on the one safe rule (exact header identifier + name),
       suggest the review band, or create one auto-created entity for a trustworthy unit.
    3. **Match new entities**: auto-created entities created since the last run (all with
       `--full`) against other entities -> merge suggestions.
    4. **Places** (`resolve-locations`), then **links and suggestions**: header identifier
       links, relationship / email-domain suggestions, event links, closing settled suggestions.

    Progress per step is recorded on the run (dataset page). Idempotent; `reset-entities`
    clears what it writes. Review on Entities -> Resolve, then Verify.
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
            counts = await resolution_workflow(
                session,
                resolved_id,
                config=config,
                link_selectors=not skip_selector_links,
                concurrency=concurrency,
                locations=not skip_locations,
                full=full,
            )
            typer.echo(json.dumps(counts, indent=2))

    asyncio.run(_run())


@app.command("resolve-locations")
def resolve_locations_cmd(
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
):
    """Attach unresolved location mentions to global place entities via the offline gazetteer.

    Per-mention lookup (countries, US/CA states, cities, regions) using the text
    around each mention; ambiguous names are left unresolved. Needs the index
    from `cipher-places-build`. Also runs at the end of `resolve-entities`.
    """

    async def _run():
        async with get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            counts = await resolve_locations_workflow(session=session, dataset_id=resolved_id)
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


@app.command("extract-signatures")
def extract_signatures_cmd(
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
    concurrency: Annotated[int, typer.Option(help="Concurrent LLM calls")] = 8,
    model: Annotated[str | None, typer.Option(help="Override the configured LLM model id")] = None,
    limit: Annotated[int | None, typer.Option(help="Only read this many emails (a trial slice)")] = None,
    include_bulk: Annotated[
        bool, typer.Option(help="Also read Gmail promotions / updates / social / forums mail (skipped by default)")
    ] = False,
    rebuild: Annotated[
        bool, typer.Option(help="Drop this dataset's signature output (not reviewed decisions) and re-read every email")
    ] = False,
):
    """Read senders' email signatures: employer -> division -> department, title, phones/emails/websites/addresses.

    A language-agnostic gate finds the sender's signature block (their name line, or the lines after a
    sign-off); the local LLM reads it verbatim, once per distinct signature. Emits mentions + relations (employed_by with role,
    part_of between units, located_in, and selectors next to the name). Run `resolve-entities` next:
    the results appear as suggestions on the organization page. Enrichment-gated (`signature_extraction`):
    each email is read once; failed model calls retry on the next run.
    """

    async def _run():
        async with get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            async with record_run(
                enrichment_type=EnrichmentType.SIGNATURE_EXTRACTION,
                dataset_id=resolved_id,
                device="na",
                unit=WorkUnit.LLM_FILE,
            ) as run:
                counts = await extract_signatures_workflow(
                    session=session,
                    dataset_id=resolved_id,
                    concurrency=concurrency,
                    model=model,
                    limit=limit,
                    rebuild=rebuild,
                    include_bulk=include_bulk,
                )
                run.units = counts["emails"]
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


@app.command("rekey")
def rekey_cmd(
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
    names: Annotated[bool, typer.Option("--names", help="Only re-key names (after a `normalize_name` change)")] = False,
    name_keys: Annotated[
        bool,
        typer.Option("--name-keys", help="Only rebuild the resolver's name-key index (after a cipher-names change)"),
    ] = False,
    selectors: Annotated[
        bool, typer.Option("--selectors", help="Only re-key selectors (after a pyselectors change)")
    ] = False,
    filetypes: Annotated[
        bool,
        typer.Option("--filetypes", help="Re-type files (after a filetyper change; opt-in, reads every file)"),
    ] = False,
    dry_run: Annotated[bool, typer.Option(help="Count what would change; write nothing")] = False,
    purge_name_keys: Annotated[
        bool, typer.Option(help="Empty the name-key index first (all datasets only; for a KEYS_VERSION bump)")
    ] = False,
):
    """Bring stored keys in line with the current normalization code (all three parts unless narrowed).

    Run after changing `normalize_name`, cipher-names, or pyselectors, so existing rows match
    what a fresh extraction would write. Names re-key mentions / entities / resolutions and trim
    name spans; name keys rebuild `entity_name_key`; selectors refresh attributes and re-key
    values that now normalize differently (folding into an existing selector). Idempotent.
    Follow a names re-key with `resolve-entities`. `--filetypes` (opt-in) re-types files after a
    filetyper change. All datasets when none is given.
    """
    flags = (names, name_keys, selectors, filetypes)
    chosen = tuple(part for part, flag in zip(REKEY_PARTS + REKEY_OPT_IN_PARTS, flags, strict=True) if flag)
    chosen = chosen or REKEY_PARTS
    if filetypes:
        ensure_stage_env("staging")

    async def _run():
        async with get_session_context() as session:
            resolved_id = None
            if dataset_name or dataset_id:
                resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            counts = await rekey_workflow(
                session, dataset_id=resolved_id, parts=chosen, dry_run=dry_run, purge_name_keys=purge_name_keys
            )
            typer.echo(json.dumps(counts, indent=2))

    asyncio.run(_run())


@app.command("retry-failed")
def retry_failed_cmd(
    enrichment_type: Annotated[EnrichmentType, typer.Argument(help="Analytic whose failed rows to retry")],
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
):
    """Put a dataset's failed rows for one analytic back to pending; re-run that step to process them."""

    async def _run():
        async with get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            count = await PostgresEnrichmentRepository(session=session).retry_failed_enrichments(
                enrichment_type=enrichment_type, dataset_id=resolved_id
            )
            typer.echo(f"{count} failed {enrichment_type.value} rows reset to pending")

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
    from cipher.utils.retrieval import RetrievalBackend

    async def _run():
        cfg = settings.retrieval
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
                progress = ((counts.get("completed", 0) + counts.get("skipped", 0)) / done) if done else 0.0
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
                file_typer=file_typer,
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


@app.command("profile-dataset")
def profile_dataset_cmd(
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID")] = None,
    all_datasets: Annotated[bool, typer.Option("--all", help="Profile every dataset")] = False,
):
    """Recompute the dataset profile behind the empty-query search briefing (docs/global-search.md §6).

    Composition, content-date histogram, the people/orgs, selectors and places mentioned in
    the most non-bulk files, top email correspondents, and a spread sample of images. A full
    recompute -- run it after enrichment changes what's in a dataset.
    """
    from sqlalchemy import text

    from cipher.datastores.postgres.repositories.dataset_profile import PostgresDatasetProfileRepository

    async def _run():
        async with get_session_context() as session:
            if all_datasets:
                dataset_ids = list((await session.execute(text("SELECT id FROM dataset ORDER BY name"))).scalars())
            else:
                dataset_ids = [await _resolve_dataset_id(session, dataset_id, dataset_name)]
            repo = PostgresDatasetProfileRepository(session=session)
            for resolved_id in dataset_ids:
                profile = await repo.compute(dataset_id=resolved_id)
                logger.success(
                    f"Profiled {resolved_id}: {profile.file_count} files, "
                    f"{len(profile.top_people_orgs)} people/orgs, {len(profile.image_sample_ids)} sample images"
                )

    asyncio.run(_run())


@app.command("prune-search-history")
def prune_search_history_cmd(
    days: Annotated[
        int,
        typer.Option(help="Keep unsaved searches run within this many days"),
    ] = settings.search.history_retention_days,
):
    """Delete unsaved search records not run recently; saved searches are kept (docs/global-search.md §7.3)."""
    from cipher.datastores.postgres.repositories.search_record import PostgresSearchRecordRepository

    async def _run():
        async with get_session_context() as session:
            deleted = await PostgresSearchRecordRepository(session=session).prune(retention_days=days)
            logger.success(f"Pruned {deleted} searches older than {days} days")

    asyncio.run(_run())


def _table_detectors(detectors: str, *, gliner_url, gliner_model_dir, nerd_url, nerd_model_dir, llm_model, device):
    from pytabular.build import ModelEndpoints, build_detectors

    endpoints = ModelEndpoints(
        gliner_url=gliner_url,
        gliner_model_dir=gliner_model_dir,
        nerd_url=nerd_url,
        nerd_model_dir=nerd_model_dir,
        llm_model=llm_model,
        device=device,
    )
    return build_detectors([d.strip() for d in detectors.split(",") if d.strip()], endpoints=endpoints)


_DetectorsOpt = Annotated[str, typer.Option(help="Comma list of: header, validators, gliner, nerd, llm")]
_GlinerUrlOpt = Annotated[str | None, typer.Option(help="pygliner service URL")]
_GlinerDirOpt = Annotated[str | None, typer.Option(help="Local GLiNER2.5 dir (in-process)")]
_NerdUrlOpt = Annotated[str | None, typer.Option(help="nerd service URL")]
_NerdDirOpt = Annotated[str | None, typer.Option(help="Local nerd model dir (in-process)")]
_LlmModelOpt = Annotated[str | None, typer.Option(help="LLM model name override (default: LLM__MODEL)")]


@app.command("profile-table")
def profile_table_cmd(
    path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="csv/tsv/xlsx/xls/ods/parquet/json/jsonl")],
    detectors: _DetectorsOpt = "header,validators",
    mapping: Annotated[
        Path | None, typer.Option(exists=True, help="Edited mapping JSON: user-set columns/slots/edges stay locked")
    ] = None,
    region: Annotated[str | None, typer.Option(help="ISO-3166 alpha-2 default region for phone numbers")] = None,
    cascade: Annotated[bool, typer.Option(help="Run model detectors only on still-ambiguous tables")] = True,
    gliner_url: _GlinerUrlOpt = settings.pytabular_gliner_url,
    gliner_model_dir: _GlinerDirOpt = settings.gliner_model_dir,
    nerd_url: _NerdUrlOpt = settings.pytabular_nerd_url,
    nerd_model_dir: _NerdDirOpt = settings.nerd_model_dir,
    llm_model: _LlmModelOpt = None,
    device: Annotated[ModelDevice, typer.Option(help="Device for in-process models")] = settings.gliner_model_device,
    summary: Annotated[bool, typer.Option(help="A readable summary instead of the full mapping JSON")] = False,
):
    """Type a table's columns onto the ontology and print the proposed mapping (no database writes).

    See docs/tabular-mapping.md.
    """
    ensure_stage_env("table-mapping")
    from pydantic import TypeAdapter
    from pytabular.decide import ProfileConfig, profile_table

    from cipher.schemas.ingestion.table_mapping import TableMapping

    locked = None
    if mapping is not None:
        raw = json.loads(mapping.read_text(encoding="utf-8"))
        locked = TypeAdapter(list[TableMapping]).validate_python(raw if isinstance(raw, list) else [raw])
    built = _table_detectors(
        detectors,
        gliner_url=gliner_url,
        gliner_model_dir=gliner_model_dir,
        nerd_url=nerd_url,
        nerd_model_dir=nerd_model_dir,
        llm_model=llm_model,
        device=device,
    )
    mappings = profile_table(path, detectors=built, locked=locked, config=ProfileConfig(region=region, cascade=cascade))
    if not summary:
        typer.echo(
            json.dumps([m.model_dump(mode="json", by_alias=True) for m in mappings], ensure_ascii=False, indent=2)
        )
        return
    for m in mappings:
        typer.echo(f"sheet={m.sheet} header_rows={m.header_rows} rows~{m.rows_estimate} fingerprint={m.fingerprint}")
        typer.echo(f"detectors: {', '.join(m.detectors)}")
        for c in m.columns:
            hit = f"{c.hit_rate:.0%}" if c.hit_rate is not None else "-"
            typer.echo(
                f"  #{c.index:<3} {c.header[:28]:<28} {c.field_type:<26} {c.confidence:.2f}  hit={hit:<5} "
                f"role={c.role or '-':<9} slot={c.slot or '-':<14} {'; '.join(c.examples[:2])[:50]}"
            )
        for s in m.slots:
            typer.echo(f"  slot {s.name}: {s.entity_type.value} <- columns {s.columns}")
        for e in m.edges:
            proposed = " (proposed verb)" if e.is_proposed_verb else ""
            typer.echo(f"  edge {e.src_slot} -{e.relationship_type}-> {e.dst_slot}{proposed}")


@app.command("map-tables")
def map_tables_cmd(
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
    detectors: _DetectorsOpt = "header,validators",
    region: Annotated[str | None, typer.Option(help="ISO-3166 alpha-2 default region for phone numbers")] = None,
    reprofile: Annotated[bool, typer.Option(help="Profile files again even if their layout is recorded")] = False,
    repropose: Annotated[
        bool, typer.Option(help="Re-run the detectors on unverified mappings (user-set parts stay locked)")
    ] = False,
    gliner_url: _GlinerUrlOpt = settings.pytabular_gliner_url,
    gliner_model_dir: _GlinerDirOpt = settings.gliner_model_dir,
    nerd_url: _NerdUrlOpt = settings.pytabular_nerd_url,
    nerd_model_dir: _NerdDirOpt = settings.nerd_model_dir,
    llm_model: _LlmModelOpt = None,
    device: Annotated[ModelDevice, typer.Option(help="Device for in-process models")] = settings.gliner_model_device,
):
    """Profile a dataset's tabular files and propose a column mapping per header layout (review them on /tables).

    Nothing reaches the graph until a mapping is verified and `cipher emit-tables` runs. See docs/tabular-mapping.md.
    """
    ensure_stage_env("table-mapping")
    from pytabular.decide import ProfileConfig

    from cipher.orchestration.extract_tables import map_tables_workflow

    built = _table_detectors(
        detectors,
        gliner_url=gliner_url,
        gliner_model_dir=gliner_model_dir,
        nerd_url=nerd_url,
        nerd_model_dir=nerd_model_dir,
        llm_model=llm_model,
        device=device,
    )

    async def _run():
        async with get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            counts = await map_tables_workflow(
                session,
                resolved_id,
                detectors=built,
                config=ProfileConfig(region=region),
                reprofile=reprofile,
                repropose=repropose,
            )
            typer.echo(json.dumps(counts, indent=2))

    asyncio.run(_run())


@app.command("emit-tables")
def emit_tables_cmd(
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
):
    """Write rows of files whose table mapping is verified: mentions, map points and edges (then run resolve-entities).

    Re-runnable: a file is re-emitted only when its mapping is verified again, replacing what it wrote before.
    """
    ensure_stage_env("table-mapping")
    from cipher.orchestration.extract_tables import emit_tables_workflow

    async def _run():
        async with get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            async with record_run(
                enrichment_type=EnrichmentType.TABLE_EXTRACTION,
                dataset_id=resolved_id,
                device="na",
                unit=WorkUnit.TABLE_ROW,
            ) as run:
                counts = await emit_tables_workflow(session, resolved_id)
                run.units = counts.get("rows", 0)
            typer.echo(json.dumps(counts, indent=2))

    asyncio.run(_run())


@app.command("summarize")
def summarize_cmd(
    dataset_name: Annotated[str | None, typer.Option(help="Dataset name to scope to")] = None,
    dataset_id: Annotated[str | None, typer.Option(help="Dataset ID to scope to")] = None,
    filetype_group: Annotated[
        list[str] | None,
        typer.Option(help="Filetype group to summarize, repeatable (default: document, email, image, table)"),
    ] = None,
    concurrency: Annotated[int, typer.Option(help="Concurrent LLM calls")] = 8,
    limit: Annotated[int | None, typer.Option(help="Only summarize this many files (a trial slice)")] = None,
    language: Annotated[str, typer.Option(help="Language the summaries are written in")] = "English",
    model: Annotated[str | None, typer.Option(help="Override the configured LLM model id")] = None,
):
    """Write a short AI summary of each file (opt-in: one LLM call per file, so it's slow on big datasets).

    Cached on the file -- re-runs and content-identical files cost nothing. Tables are summarized from
    their sample rows + column mapping (run `cipher map-tables` first). One file at a time: the file
    viewer's Summarize button.
    """
    from cipher.orchestration.summarize import summarize_workflow

    groups = filetype_group or list(DEFAULT_FILETYPE_GROUPS[EnrichmentType.TEXT_SUMMARIZATION])

    async def _run():
        async with get_session_context() as session:
            resolved_id = await _resolve_dataset_id(session, dataset_id, dataset_name)
            async with record_run(
                enrichment_type=EnrichmentType.TEXT_SUMMARIZATION,
                dataset_id=resolved_id,
                device="na",
                unit=WorkUnit.LLM_FILE,
                params={"filetype_groups": groups, "language": language, "model": model},
            ) as run:
                counts = await summarize_workflow(
                    session,
                    resolved_id,
                    filetype_groups=groups,
                    concurrency=concurrency,
                    limit=limit,
                    language=language,
                    model=model,
                )
                run.units = counts["llm_calls"]
            typer.echo(json.dumps(counts, indent=2))

    asyncio.run(_run())


@app.command("eval-table-typing")
def eval_table_typing_cmd(
    labels: Annotated[
        Path | None, typer.Option(exists=True, help="labels.yaml of hand-labelled files (default: synthetic tables)")
    ] = None,
    combos: Annotated[
        str,
        typer.Option(help="Semicolon list of detector combos to compare, e.g. 'header;validators;header,validators'"),
    ] = "header;validators;header,validators",
    synthetic: Annotated[int, typer.Option(help="Synthetic tables to generate when no labels are given")] = 42,
    seed: Annotated[int, typer.Option(help="Synthetic table seed")] = 7,
    out_dir: Annotated[
        Path | None, typer.Option(help="Where synthetic tables are written (default: a temp dir)")
    ] = None,
    cascade: Annotated[
        bool, typer.Option(help="Cascade inside a combo (off: every detector sees every column)")
    ] = False,
    gliner_url: _GlinerUrlOpt = settings.pytabular_gliner_url,
    gliner_model_dir: _GlinerDirOpt = settings.gliner_model_dir,
    nerd_url: _NerdUrlOpt = settings.pytabular_nerd_url,
    nerd_model_dir: _NerdDirOpt = settings.nerd_model_dir,
    llm_model: _LlmModelOpt = None,
    device: Annotated[ModelDevice, typer.Option(help="Device for in-process models")] = settings.gliner_model_device,
    mistakes: Annotated[int, typer.Option(help="Most common mistakes to list per combo")] = 10,
):
    """Compare column-typing detectors on labelled or synthetic messy tables (accuracy, macro-F1, ms/column)."""
    ensure_stage_env("table-mapping")
    import tempfile

    from pytabular.decide import ProfileConfig
    from pytabular.evaluate import LabelledTable, evaluate, load_labels, report
    from pytabular.synth import make_tables

    if labels is not None:
        tables = load_labels(labels)
    else:
        directory = out_dir or Path(tempfile.mkdtemp(prefix="pytabular-synth-"))
        tables = [
            LabelledTable(path=t.path, labels=dict(enumerate(t.labels)))
            for t in make_tables(directory, count=synthetic, seed=seed)
        ]
        logger.info(f"Generated {len(tables)} synthetic tables in {directory}")

    cache: dict[str, object] = {}

    def detector(name: str):
        if name not in cache:
            cache[name] = _table_detectors(
                name,
                gliner_url=gliner_url,
                gliner_model_dir=gliner_model_dir,
                nerd_url=nerd_url,
                nerd_model_dir=nerd_model_dir,
                llm_model=llm_model,
                device=device,
            )[0]
        return cache[name]

    combo_map = {
        combo.strip(): [detector(n.strip()) for n in combo.split(",") if n.strip()]
        for combo in combos.split(";")
        if combo.strip()
    }
    results = evaluate(tables, combo_map, config=ProfileConfig(cascade=cascade))
    typer.echo(report(results, mistakes=mistakes))


if __name__ == "__main__":
    app()
