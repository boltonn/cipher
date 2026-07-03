"""Simple CLI for test-driving the ingestion + embedding + face-detection pipeline.

Deliberately minimal, and safe to run in any order or run twice: loading is
upsert-based (re-running on the same path is a no-op), and both the
embedding and face-detection commands dedupe by content hash before doing
any real work, so the same photo ingested more than once is only ever
embedded/detected once.
"""

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from loguru import logger

from cipher.datastores.postgres.repositories import PostgresDatasetRepository
from cipher.orchestration.detect_faces import (
    detect_faces_workflow,
    get_face_detection_stats,
)
from cipher.orchestration.embed_images import embed_images_workflow, get_embedding_stats
from cipher.orchestration.ingest import load_files_workflow
from cipher.orchestration.schema import create_tables
from cipher.orchestration.session import get_session_context
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


@app.command("load-images")
def load_images(
    path: Annotated[Path, typer.Argument(help="Local directory of images to load")],
    dataset_name: Annotated[str, typer.Option(help="Dataset to create or reuse")],
    limit: Annotated[int | None, typer.Option(help="Max number of files to load")] = None,
):
    """Ingest a directory of files into a dataset (File rows only; no analysis)."""
    from filetyper.models.main import FileTyper

    async def _run():
        file_typer = FileTyper()
        async with get_session_context() as session:
            dataset_id = await load_files_workflow(
                session=session,
                path=path,
                file_analyzer=file_typer.generate_from_local_path,
                dataset_name=dataset_name,
                limit=limit,
            )
            logger.success(f"Dataset ready: {dataset_id}")

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

    asyncio.run(_run())


if __name__ == "__main__":
    app()
