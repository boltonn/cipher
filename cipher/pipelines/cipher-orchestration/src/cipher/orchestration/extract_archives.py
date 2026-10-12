"""Archive extraction: unpack archives into member files, and decode compressed single files in place.

One `archive_extraction` row per archive (zip, tar, compressed tar) and per file found
compressed (`report.csv.gz`). Members become ordinary `file` rows: `parent_id` is the archive,
`path` is where they were found (`<archive path>/<member path>`, display only), `uri` is where
they were stored. A member that is itself an archive (or compressed) is queued by the next pass, never
opened recursively in-process, so every level gets the same guards:

* depth -- more than `max_depth` ancestors on the `parent_id` chain: skipped.
* cycle -- same content as an ancestor (a quine, A -> B -> A): skipped.
* duplicate -- same content as a file in the dataset already extracted: skipped (its own row
  records the sighting; the members hang off the first copy).

An interrupted run resumes: its claims go back to pending (`record_run`), members already
recorded for an archive are skipped by display path, and scratch files it left are swept.

Encrypted members are tried with each password in the passwords file (one per line). When that
file changes, archives that held encrypted members are queued again and only what is still
missing is extracted.
Limits (bombs, disk) stop one archive -- marked failed with why -- never the run.
"""

import re
from collections import Counter
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from itertools import islice
from pathlib import Path
from typing import TYPE_CHECKING

import anyio
from loguru import logger
from sqlalchemy import and_, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from tqdm import tqdm

from cipher.datastores.postgres.repositories import (
    PostgresEnrichmentRepository,
    PostgresEnrichmentRunRepository,
    PostgresFileRepository,
)
from cipher.datastores.postgres.tables.enrichment import EnrichmentTable
from cipher.datastores.postgres.tables.file import FileTable
from cipher.schemas.ingestion.enrichment import EnrichableType, EnrichmentType, ProcessingStatus
from cipher.schemas.ingestion.file import CompressionInfo, FileCreate
from cipher.utils.output import OutputStore
from cipher.utils.uri import local_copy, open_binary, to_uri

if TYPE_CHECKING:
    from filetyper.models.main import FileTyper
    from pyarchive import ArchiveLimits, ArchiveProgress, ExtractedMember

DEFAULT_MAX_DEPTH = 5
MISSING = "missing: "  # failure reason prefix: a tool isn't installed; such archives are retried every run
MEMBERS_KEPT = re.compile(r" \([\d,]+ members kept\)$")
GIB = 1 << 30
MEMBER_BATCH = 500
PROGRESS_WRITE_SECONDS = 2.0
_CHAIN_LIMIT = 64

_ANCESTORS = text(
    """
    WITH RECURSIVE chain(id, parent_id, sha256, depth) AS (
        SELECT id, parent_id, sha256, 0 FROM file WHERE id = :file_id
        UNION ALL
        SELECT f.id, f.parent_id, f.sha256, chain.depth + 1
        FROM file f JOIN chain ON f.id = chain.parent_id
        WHERE chain.depth < :limit
    )
    SELECT sha256 FROM chain WHERE depth > 0
    """
)


def _is_undecoded(file: type[FileTable] = FileTable):  # noqa: ANN202 -- SQL expression
    """Found compressed and still holding the compressed bytes (decoding rewrites `sha256`)."""
    return and_(file.compression.is_not(None), file.compression["sha256"].astext == file.sha256)


async def queue_archive_extraction(session: AsyncSession, dataset_id: str) -> int:
    """Queue every archive (installed tools or not) and every not-yet-decoded compressed file without a row yet."""
    from pyarchive import archive_filetypes

    queued = select(EnrichmentTable.id).where(
        EnrichmentTable.enrichable_id == FileTable.id,
        EnrichmentTable.enrichable_type == EnrichableType.FILE,
        EnrichmentTable.enrichment_type == EnrichmentType.ARCHIVE_EXTRACTION,
    )
    file_ids = (
        await session.scalars(
            select(FileTable.id).where(
                FileTable.dataset_id == dataset_id,
                FileTable.filetype.in_(archive_filetypes()) | _is_undecoded(),
                ~queued.exists(),
            )
        )
    ).all()
    if file_ids:
        await PostgresEnrichmentRepository(session=session).queue_enrichments_for_files(
            file_ids=list(file_ids), enrichment_type=EnrichmentType.ARCHIVE_EXTRACTION
        )
    await session.commit()
    return len(file_ids)


def _missing_rows(dataset_id: str):  # noqa: ANN202 -- SQL expression
    """Archive extractions that failed for a tool that wasn't installed (`missing: ...`)."""
    return and_(
        EnrichmentTable.enrichment_type == EnrichmentType.ARCHIVE_EXTRACTION,
        EnrichmentTable.enrichable_type == EnrichableType.FILE,
        EnrichmentTable.status == ProcessingStatus.FAILED,
        EnrichmentTable.error_message.startswith(MISSING),
        select(FileTable.id)
        .where(FileTable.id == EnrichmentTable.enrichable_id, FileTable.dataset_id == dataset_id)
        .exists(),
    )


async def missing_dependencies(session: AsyncSession, dataset_id: str) -> dict[str, int]:
    """What the dataset's archives still need installed -> how many archives wait on it."""
    reasons = (await session.scalars(select(EnrichmentTable.error_message).where(_missing_rows(dataset_id)))).all()
    return dict(Counter(MEMBERS_KEPT.sub("", reason).removeprefix(MISSING) for reason in reasons))


class _RunProgress:
    """Live progress of the archive in flight, mirrored onto `enrichment_run.progress` every few seconds."""

    def __init__(self, engine: AsyncEngine, run_id: str | None, total: int) -> None:
        self.engine, self.run_id = engine, run_id
        self.state: dict = {"archives_done": 0, "archives_total": total, "current": None}
        self._written: dict | None = None

    def update(self, file: dict, progress: "ArchiveProgress") -> None:
        """Called from the extraction thread with throttled progress."""
        self.state["current"] = {"file_id": file["id"], "filename": file["filename"], **progress.model_dump()}

    async def write_forever(self) -> None:
        """Write whenever something changed; cancelled when the run ends."""
        while True:
            await self.write()
            await anyio.sleep(PROGRESS_WRITE_SECONDS)

    async def write(self) -> None:
        """Write the current state if it changed."""
        if self.run_id is None or self.state == self._written:
            return
        snapshot = {**self.state, "current": dict(self.state["current"]) if self.state["current"] else None}
        async with AsyncSession(self.engine) as session:
            await PostgresEnrichmentRunRepository(session=session).set_progress(self.run_id, {"archives": snapshot})
        self._written = snapshot


async def extract_archives_workflow(
    session: AsyncSession,
    dataset_id: str,
    store: OutputStore,
    limits: "ArchiveLimits",
    max_depth: int = DEFAULT_MAX_DEPTH,
    run_id: str | None = None,
    passwords_file: Path | None = None,
) -> Counter:
    """Unpack the dataset's archives, pass after pass, until no archive (or compressed file) is pending.

    Args:
        session: Database session.
        dataset_id: The dataset.
        store: Where member bytes go.
        limits: Bomb and disk guards.
        max_depth: Most archives-within-archives levels to open.
        run_id: The `enrichment_run` progress is written to.
        passwords_file: Passwords for encrypted members, one per line.

    Returns:
        Counts: archives, members, decoded, skipped / failed (by reason), member_skips by reason.
    """
    from filetyper.models.main import FileTyper

    if swept := store.sweep_tmp():
        logger.info(f"Removed {swept} scratch file(s) left by an interrupted run")
    file_typer = FileTyper()
    enrichment_repo = PostgresEnrichmentRepository(session=session)
    counts: Counter = Counter()
    retried = await session.execute(
        update(EnrichmentTable)
        .where(_missing_rows(dataset_id))
        .values(status=ProcessingStatus.PENDING, error_message=None, date_updated=datetime.now(UTC))
    )
    await session.commit()
    if retried.rowcount:
        logger.info(f"Retrying {retried.rowcount} archive(s) that waited on a missing tool")
    passwords = load_passwords(passwords_file)
    if passwords and (requeued := await _requeue_encrypted(session, dataset_id, passwords_file)):
        logger.info(f"Passwords file changed: {requeued} archive(s) with encrypted members queued again")
        counts["requeued_encrypted"] = requeued
    while await queue_archive_extraction(session, dataset_id) or await _pending(enrichment_repo, dataset_id):
        total = await _pending(enrichment_repo, dataset_id)
        progress = _RunProgress(session.bind, run_id, total)
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(progress.write_forever)
            with tqdm(total=total, desc=f"Unpacking (pass {counts['passes'] + 1})", unit=" archive") as pbar:
                while batch := await enrichment_repo.get_pending_batch(
                    enrichment_type=EnrichmentType.ARCHIVE_EXTRACTION,
                    enrichable_type=EnrichableType.FILE,
                    batch_size=1,
                    dataset_id=dataset_id,
                    max_retries=0,  # a failed archive waits for `retry-failed`, never re-read in the same run
                ):
                    item = batch[0]
                    await enrichment_repo.mark_processing(enrichment_ids=[item.enrichment.id])
                    await session.commit()
                    status, reason = await _process(
                        session, item.resource, store, limits, max_depth, file_typer, progress, counts, passwords
                    )
                    if status == ProcessingStatus.COMPLETED:
                        await enrichment_repo.mark_completed_batch([item.enrichment.id])
                    elif status == ProcessingStatus.SKIPPED:
                        await enrichment_repo.mark_skipped({item.enrichment.id: reason})
                    else:
                        await enrichment_repo.mark_failed({item.enrichment.id: reason})
                    await session.commit()
                    counts[
                        status.value
                        if status == ProcessingStatus.COMPLETED
                        else f"{status.value}:{reason.split(':')[0]}"
                    ] += 1
                    progress.state["archives_done"] += 1
                    pbar.update(1)
                    pbar.set_postfix(members=counts["members"])
            await progress.write()
            tasks.cancel_scope.cancel()
        counts["passes"] += 1
    logger.success(f"Unpacked archives for dataset {dataset_id}: {dict(counts)}")
    for need, archives in (await missing_dependencies(session, dataset_id)).items():
        logger.error(f"{archives} archive(s) not unpacked: {need}")
    return counts


def load_passwords(path: Path | None) -> list[str]:
    """The passwords file's lines, in order (blank lines dropped); none when there is no file."""
    if path is None or not (path := path.expanduser()).is_file():
        return []
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line]


async def _requeue_encrypted(session: AsyncSession, dataset_id: str, passwords_file: Path) -> int:
    """Queue again the archives left with encrypted members (or an encrypted listing) since the passwords changed."""
    changed = datetime.fromtimestamp(passwords_file.expanduser().stat().st_mtime, tz=UTC)
    result = await session.execute(
        update(EnrichmentTable)
        .where(
            EnrichmentTable.enrichment_type == EnrichmentType.ARCHIVE_EXTRACTION,
            EnrichmentTable.enrichable_type == EnrichableType.FILE,
            func.coalesce(EnrichmentTable.date_completed, EnrichmentTable.date_updated) < changed,
            or_(
                and_(
                    EnrichmentTable.status == ProcessingStatus.COMPLETED,
                    select(FileTable.id)
                    .where(FileTable.id == EnrichmentTable.enrichable_id, FileTable.is_encrypted)
                    .exists(),
                ),
                and_(
                    EnrichmentTable.status == ProcessingStatus.SKIPPED,
                    EnrichmentTable.error_message.startswith("encrypted:"),
                ),
            ),
            select(FileTable.id)
            .where(FileTable.id == EnrichmentTable.enrichable_id, FileTable.dataset_id == dataset_id)
            .exists(),
        )
        .values(status=ProcessingStatus.PENDING, error_message=None, date_updated=datetime.now(UTC))
    )
    await session.commit()
    return result.rowcount


async def _pending(enrichment_repo: PostgresEnrichmentRepository, dataset_id: str) -> int:
    return await enrichment_repo.count_pending(
        enrichment_type=EnrichmentType.ARCHIVE_EXTRACTION, enrichable_type=EnrichableType.FILE, dataset_id=dataset_id
    )


async def _process(
    session: AsyncSession,
    file: dict,
    store: OutputStore,
    limits: "ArchiveLimits",
    max_depth: int,
    file_typer: "FileTyper",
    progress: _RunProgress,
    counts: Counter,
    passwords: Sequence[str] = (),
) -> tuple[ProcessingStatus, str]:
    """One archive or compressed file -> (status, reason)."""
    from filetyper.encryption import is_encrypted
    from pyarchive import ArchiveError, MissingDependencyError, decode_to_store, missing_dependency, supported_filetypes

    ancestors = (await session.scalars(_ANCESTORS, {"file_id": file["id"], "limit": _CHAIN_LIMIT})).all()
    if len(ancestors) > max_depth:
        return ProcessingStatus.SKIPPED, f"depth: {len(ancestors)} levels deep (max {max_depth})"
    if file["sha256"] in ancestors:
        return ProcessingStatus.SKIPPED, "cycle: same content as the archive it was found in"

    if (missing := missing_dependency(file["filetype"])) is not None:
        return ProcessingStatus.FAILED, MISSING + missing
    compression = CompressionInfo.model_validate(file["compression"]) if file.get("compression") else None
    if file["filetype"] not in supported_filetypes():
        if compression is None or compression.sha256 != file["sha256"]:
            return ProcessingStatus.SKIPPED, "nothing: not an archive and not compressed"
        if (copied := await _copy_decoded(session, file)) is not None:
            counts["decoded"] += 1
            return ProcessingStatus.COMPLETED, copied
        try:
            stored = await anyio.to_thread.run_sync(
                lambda: decode_to_store(
                    to_uri(file["uri"]),
                    compression.encoding,
                    store,
                    limits,
                    on_progress=lambda p: progress.update(file, p),
                )
            )
        except MissingDependencyError as e:
            return ProcessingStatus.FAILED, MISSING + str(e)
        except ArchiveError as e:
            return ProcessingStatus.FAILED, str(e) if str(e).startswith("limit:") else f"corrupt: {e}"
        with open_binary(stored.uri) as decoded:
            encrypted = is_encrypted(decoded, file["filetype"])
        await session.execute(
            update(FileTable)
            .where(FileTable.id == file["id"])
            .values(uri=stored.uri, md5=stored.md5, sha256=stored.sha256, size=stored.size, is_encrypted=encrypted)
        )
        counts["decoded"] += 1
        return ProcessingStatus.COMPLETED, "decoded"

    if (first := await _extracted_copy(session, file)) is not None:
        return ProcessingStatus.SKIPPED, f"duplicate: same content as file {first}"
    return await _extract_members(session, file, compression, store, limits, file_typer, progress, counts, passwords)


async def _copy_decoded(session: AsyncSession, file: dict) -> str | None:
    """Reuse the decoded file of another file found with the same compressed bytes (any dataset)."""
    sibling = (
        await session.execute(
            select(FileTable.uri, FileTable.md5, FileTable.sha256, FileTable.size)
            .where(
                FileTable.compression["sha256"].astext == file["sha256"],
                FileTable.sha256 != file["sha256"],
            )
            .limit(1)
        )
    ).first()
    if sibling is None:
        return None
    await session.execute(update(FileTable).where(FileTable.id == file["id"]).values(**sibling._asdict()))
    return "decoded (same compressed bytes as an already-decoded file)"


async def _extracted_copy(session: AsyncSession, file: dict) -> str | None:
    """Another file in the dataset with the same content whose extraction is done or under way."""
    return await session.scalar(
        select(FileTable.id)
        .join(
            EnrichmentTable,
            and_(
                EnrichmentTable.enrichable_id == FileTable.id,
                EnrichmentTable.enrichable_type == EnrichableType.FILE,
                EnrichmentTable.enrichment_type == EnrichmentType.ARCHIVE_EXTRACTION,
            ),
        )
        .where(
            FileTable.dataset_id == file["dataset_id"],
            FileTable.sha256 == file["sha256"],
            FileTable.id != file["id"],
            EnrichmentTable.status.in_([ProcessingStatus.COMPLETED, ProcessingStatus.PROCESSING]),
        )
        .limit(1)
    )


async def _extract_members(
    session: AsyncSession,
    file: dict,
    compression: CompressionInfo | None,
    store: OutputStore,
    limits: "ArchiveLimits",
    file_typer: "FileTyper",
    progress: _RunProgress,
    counts: Counter,
    passwords: Sequence[str],
) -> tuple[ProcessingStatus, str]:
    """Stream members into the store and upsert their rows in batches (each batch is a resume checkpoint)."""
    from pyarchive import (
        ArchiveEncryptedError,
        ArchiveError,
        ArchiveLimitError,
        MissingDependencyError,
        SandboxUnavailableError,
        UnsupportedArchiveError,
        extract,
    )

    prefix = f"{file['path'].rstrip('/')}/"
    recorded = {
        path.removeprefix(prefix)
        for path in (await session.scalars(select(FileTable.path).where(FileTable.parent_id == file["id"]))).all()
    }
    members = extract(
        to_uri(file["uri"]),
        file["filetype"],
        store,
        compression=compression.encoding if compression else None,
        limits=limits,
        skip=recorded.__contains__,
        on_progress=lambda p: progress.update(file, p),
        passwords=passwords,
    )
    file_repo = PostgresFileRepository(session=session)
    written, encrypted = 0, Counter()
    try:
        exhausted = False
        while not exhausted:
            chunk, exhausted = await anyio.to_thread.run_sync(
                _next_rows, members, file, prefix, file_typer, counts, encrypted
            )
            await file_repo.bulk_upsert_files(chunk)
            written += len(chunk)
    except UnsupportedArchiveError as e:
        return ProcessingStatus.SKIPPED, f"unsupported: {e}"
    except ArchiveEncryptedError as e:
        encrypted["listing"] += 1
        return ProcessingStatus.SKIPPED, f"encrypted: {e}"
    except MissingDependencyError as e:
        return ProcessingStatus.FAILED, f"{MISSING}{e} ({written:,} members kept)"
    except SandboxUnavailableError as e:
        return ProcessingStatus.FAILED, f"sandbox: {e}"
    except ArchiveLimitError as e:
        return ProcessingStatus.FAILED, f"{e} ({written:,} members kept)"
    except ArchiveError as e:
        return ProcessingStatus.FAILED, f"corrupt: {e} ({written:,} members kept)"
    finally:
        members.close()
        if any(encrypted.values()):
            await session.execute(update(FileTable).where(FileTable.id == file["id"]).values(is_encrypted=True))
            await session.commit()
    counts["members"] += written
    return ProcessingStatus.COMPLETED, ""


def _next_rows(
    members: Iterator["ExtractedMember"],
    file: dict,
    prefix: str,
    file_typer: "FileTyper",
    counts: Counter,
    encrypted: Counter,
) -> tuple[list[FileCreate], bool]:
    """The next batch of members as file rows, and whether the archive is exhausted (runs in a worker thread)."""
    rows, seen = [], 0
    for member in islice(members, MEMBER_BATCH):
        seen += 1
        encrypted["members"] += member.is_encrypted
        if member.stored is None:
            counts[f"member_skip:{member.skip_reason.value}"] += 1
            continue
        with local_copy(member.stored.uri) as member_file:
            described = file_typer.describe(
                md5=member.stored.md5,
                sha256=member.stored.sha256,
                size=member.stored.size,
                path=member_file,
                name=member.filename,
            )
        rows.append(
            FileCreate(
                dataset_id=file["dataset_id"],
                parent_id=file["id"],
                filename=member.filename,
                path=prefix + member.member_path,
                uri=member.stored.uri,
                md5=member.stored.md5,
                sha256=member.stored.sha256,
                size=member.stored.size,
                filetype=described["filetype"],
                filetype_group=described["filetype_group"],
                filetype_name=described.get("filetype_name"),
                mime_type=described["mime_type"] or "application/octet-stream",
                compression=described["compression"],
                is_encrypted=described["is_encrypted"],  # a decrypted member's bytes need no password
                date_last_updated=member.date_last_updated,
                date_created=member.date_created,
            )
        )
    return rows, seen < MEMBER_BATCH
