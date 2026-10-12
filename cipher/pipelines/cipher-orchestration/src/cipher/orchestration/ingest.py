"""File ingestion workflow - orchestrates loading and analysis."""

import asyncio
import hashlib
from collections.abc import Awaitable, Callable, Sequence
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

import anyio
from loguru import logger
from sqlalchemy import select

from cipher.datastores.postgres.repositories import (
    PostgresDatasetRepository,
    PostgresFileRepository,
)
from cipher.datastores.postgres.tables.file import FileTable
from cipher.schemas.ingestion.dataset import Dataset, DatasetCreate
from cipher.schemas.ingestion.file import FileCreate
from cipher.utils.uri import MAX_IN_MEMORY_BYTES, FoundFile, is_local, list_files, local_copy, local_path, read_bytes

if TYPE_CHECKING:
    from filetyper.models.main import FileTyper
    from sqlalchemy.ext.asyncio import AsyncSession


async def create_dataset(
    session: "AsyncSession",
    name: str,
    description: str | None = None,
) -> Dataset:
    """Create a new dataset and return it."""
    dataset_repo = PostgresDatasetRepository(session=session)
    dataset_create = DatasetCreate(name=name, description=description)
    dataset = await dataset_repo.add_dataset(dataset=dataset_create)
    await session.commit()
    logger.success(f"Created dataset: {dataset.name} (ID: {dataset.id})")
    return dataset


async def get_dataset(
    session: "AsyncSession",
    dataset_id: str,
) -> Dataset | None:
    """Retrieve an existing dataset by ID."""
    dataset_repo = PostgresDatasetRepository(session=session)
    return await dataset_repo.get_dataset_by_id(dataset_id=dataset_id)


def _file_create(file_typer: "FileTyper", found: FoundFile, *, dataset_id: str) -> FileCreate:
    """Type and hash one found file: by path when local, from bytes (or a temp copy if huge) when remote."""
    name = PurePosixPath(found.relative_path).name
    if is_local(found.uri):
        path = local_path(found.uri)
        info = file_typer.get_file_info(path)
        location, uri = path.resolve().as_posix(), path.as_uri()
    elif found.size <= MAX_IN_MEMORY_BYTES:
        data = read_bytes(found.uri)
        md5, sha256 = hashlib.md5(data).hexdigest(), hashlib.sha256(data).hexdigest()
        described = file_typer.describe(md5=md5, sha256=sha256, size=len(data), data=data, name=name)
        info = {**described, "md5": md5, "sha256": sha256, "size": len(data)}
        location, uri = "/" + found.uri.removeprefix("s3://"), found.uri
    else:
        with local_copy(found.uri) as copy:
            info = file_typer.get_file_info(copy, name=name)
        location, uri = "/" + found.uri.removeprefix("s3://"), found.uri
    return FileCreate(
        dataset_id=dataset_id,
        filename=name,
        path=location,
        uri=uri,
        device=None if is_local(uri) else uri.removeprefix("s3://").split("/", 1)[0],
        filetype_group=info["filetype_group"],
        filetype=info["filetype"],
        filetype_name=info.get("filetype_name"),
        md5=info["md5"],
        sha256=info["sha256"],
        mime_type=info["mime_type"],
        size=info["size"],
        date_created=found.date_modified,
        date_last_updated=found.date_modified,
        compression=info.get("compression"),
        is_encrypted=info["is_encrypted"],
    )


async def load_files(
    session: "AsyncSession",
    uri: str,
    *,
    dataset_id: str,
    file_typer: "FileTyper",
    include: Sequence[str] = (),
    exclude: Sequence[str] = (),
    limit: int | None = None,
    batch_size: int = 100,
    concurrency: int = 16,
    on_progress: Callable[[dict], Awaitable[None]] | None = None,
) -> int:
    """Crawl a directory or `s3://bucket/prefix/` into `file` rows (typed and hashed, nothing copied).

    Files already staged (same `path`) are skipped, so an interrupted crawl resumes.

    Args:
        session: Database session.
        uri: Where the files are (read-only).
        dataset_id: Dataset to stage into.
        file_typer: The filetyper.
        include: Globs a file's path below `uri` must match (any).
        exclude: Globs that drop a file.
        limit: Stop after this many new files.
        batch_size: Files typed (concurrently) and written per round trip.
        concurrency: Files typed at once (remote reads overlap).
        on_progress: Awaited with `{found, staged, already_staged, is_listing_done}` after each batch.

    Returns:
        The number of files staged by this run.
    """
    file_repo = PostgresFileRepository(session=session)
    staged_paths = set(
        (await session.scalars(select(FileTable.path).where(FileTable.dataset_id == dataset_id))).all()
    )
    limiter = anyio.CapacityLimiter(concurrency)
    progress = {"found": 0, "staged": 0, "already_staged": 0, "is_listing_done": False}

    async def type_one(found: FoundFile) -> FileCreate:
        return await anyio.to_thread.run_sync(
            lambda: _file_create(file_typer, found, dataset_id=dataset_id), limiter=limiter
        )

    async def flush(batch: list[FoundFile]) -> None:
        creates = await asyncio.gather(*(type_one(found) for found in batch))
        await file_repo.bulk_upsert_files(list(creates))
        progress["staged"] += len(creates)
        if on_progress:
            await on_progress(dict(progress))

    batch: list[FoundFile] = []
    async for found in list_files(uri, include=include, exclude=exclude):
        progress["found"] += 1
        location = (
            local_path(found.uri).resolve().as_posix() if is_local(found.uri) else "/" + found.uri.removeprefix("s3://")
        )
        if location in staged_paths:
            progress["already_staged"] += 1
            continue
        batch.append(found)
        if limit is not None and progress["staged"] + len(batch) >= limit:
            break
        if len(batch) >= batch_size:
            await flush(batch)
            batch = []
    progress["is_listing_done"] = True
    if batch:
        await flush(batch)
    elif on_progress:
        await on_progress(dict(progress))

    if progress["staged"]:
        await PostgresDatasetRepository(session=session).mark_staged(dataset_id=dataset_id)
    logger.success(
        f"Staged {progress['staged']} files into dataset {dataset_id} "
        f"({progress['already_staged']} already staged, {progress['found']} found)"
    )
    return progress["staged"]
