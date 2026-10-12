"""Pick the backend for an archive's filetype.

The archive may be local or remote (`s3://`): zip / tar / mbox read a remote archive as a
seekable stream (only the byte ranges they need), while `7zz` gets a local temp copy.
"""

import os
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path

from filetyper.compression import MISSING_DECODERS

from cipher.schemas.ingestion.file import Compression
from cipher.utils.output import OutputStore
from cipher.utils.uri import Uri, is_local, local_copy
from pyarchive.backends.mbox import iter_mbox
from pyarchive.backends.sevenzip import SEVENZIP_FILETYPES, SEVENZIP_NEEDED, find_sevenzip, iter_sevenzip
from pyarchive.backends.stdlib import iter_tar, iter_zip
from pyarchive.schemas import (
    GIB,
    ArchiveLimit,
    ArchiveLimitError,
    ArchiveLimits,
    ArchiveProgress,
    ExtractedMember,
    MemberSkipReason,
    MissingDependencyError,
    UnsupportedArchiveError,
)

STDLIB_FILETYPES: frozenset[str] = frozenset({"zip", "tar", "mbox"})

REMOTE_MAX_ARCHIVE_GIB = 50.0
"""Default size limit for a remote archive: 7z / rar / iso are copied locally before 7zz reads them."""


def max_archive_bytes(path: Path | Uri, limits: ArchiveLimits) -> int | None:
    """The size above which this archive isn't opened: the limit given, PYARCHIVE_MAX_ARCHIVE_GIB, else by location."""
    if limits.max_archive_bytes is not None:
        return limits.max_archive_bytes
    if configured := os.environ.get("PYARCHIVE_MAX_ARCHIVE_GIB"):
        return int(float(configured) * GIB)
    return None if is_local(path) else int(REMOTE_MAX_ARCHIVE_GIB * GIB)


def _sevenzip(path: Path | Uri, *args, **kwargs) -> Iterator[ExtractedMember]:
    """`iter_sevenzip` on a local path, copying a remote archive to a temp file first."""
    with local_copy(path) as local:
        yield from iter_sevenzip(local, *args, **kwargs)


def supported_filetypes() -> frozenset[str]:
    """Filetypes this install can open: zip / tar / mbox always, 7z / rar / iso / ... when `7zz` is found."""
    return STDLIB_FILETYPES | (SEVENZIP_FILETYPES if find_sevenzip() else frozenset())


def archive_filetypes() -> frozenset[str]:
    """Every filetype archive extraction handles, installed or not (a missing tool is an error, not a skip)."""
    return STDLIB_FILETYPES | SEVENZIP_FILETYPES | frozenset(MISSING_DECODERS)


def missing_dependency(filetype: str) -> str | None:
    """What has to be installed to open this filetype here, or None when nothing is missing."""
    if filetype in SEVENZIP_FILETYPES and find_sevenzip() is None:
        return f"{filetype} needs {SEVENZIP_NEEDED}"
    if filetype in MISSING_DECODERS:
        return f"{filetype} needs {MISSING_DECODERS[filetype]}"
    return None


def extract(
    path: Path | Uri,
    filetype: str,
    store: OutputStore,
    *,
    compression: Compression | None = None,
    limits: ArchiveLimits | None = None,
    skip: Callable[[str], bool] | None = None,
    on_progress: Callable[[ArchiveProgress], None] | None = None,
    passwords: Sequence[str] = (),
) -> Iterator[ExtractedMember]:
    """Stream an archive's members into the output store, one `ExtractedMember` per regular member.

    Nested archives are not opened: a member that is itself an archive is just a member.

    Args:
        path: The archive as found: a local path or a remote `Uri`.
        filetype: Its filetype (`zip`, `tar`, `mbox`, `sevenzip`, `rar`, `iso`, ...); a `.tar.gz` is `tar` with `compression`.
        store: Where member bytes go.
        compression: The single-stream compression the archive was found in, if any.
        limits: Bomb / disk guards (defaults to `ArchiveLimits()`).
        skip: Given a member's display path, True to skip it (already recorded by an interrupted run).
        on_progress: Called with throttled progress inside the archive.
        passwords: Tried in order on encrypted members (and an encrypted 7z / rar listing).

    Yields:
        Each member, written or skipped with a reason.

    Raises:
        MissingDependencyError: A tool it needs isn't installed (7z / rar / iso, and AES or deflate64 zip
            members, need `7zz`; .zst / .lz4 their decoders); the message says what to install.
        UnsupportedArchiveError: No backend reads this filetype.
        ArchiveEncryptedError: The archive's listing is encrypted and no password opens it.
        ArchiveLimitError: A limit tripped (members yielded before it are kept), or the archive is
            bigger than `max_archive_bytes` (nothing opened).
        ArchiveCorruptError: Unreadable past some point (members yielded before it are kept).
    """
    limits = limits or ArchiveLimits()
    if (missing := missing_dependency(filetype)) is not None:
        raise MissingDependencyError(missing)
    if (limit := max_archive_bytes(path, limits)) is not None and path.stat().st_size > limit:
        raise ArchiveLimitError(ArchiveLimit.ARCHIVE_BYTES, f"archive larger than {limit / GIB:g} GiB")
    match filetype:
        case "zip":
            yield from _zip(path, store, limits, skip, on_progress, passwords)
        case "tar":
            yield from iter_tar(path, store, limits, compression=compression, skip=skip, on_progress=on_progress)
        case "mbox":
            yield from iter_mbox(path, store, limits, compression=compression, skip=skip, on_progress=on_progress)
        case _ if filetype in SEVENZIP_FILETYPES:
            yield from _sevenzip(path, store, limits, skip=skip, on_progress=on_progress, passwords=passwords)
        case _:
            raise UnsupportedArchiveError(f"no backend for {filetype!r}")


def _zip(
    path: Path | Uri,
    store: OutputStore,
    limits: ArchiveLimits,
    skip: Callable[[str], bool] | None,
    on_progress: Callable[[ArchiveProgress], None] | None,
    passwords: Sequence[str],
) -> Iterator[ExtractedMember]:
    """The stdlib reads the zip; members in a method it can't (deflate64, AES, ...) then go to 7zz (an error without it)."""
    unreadable: dict[str, ExtractedMember] = {}
    for member in iter_zip(path, store, limits, skip=skip, on_progress=on_progress, passwords=passwords):
        if member.skip_reason == MemberSkipReason.UNSUPPORTED_METHOD:
            unreadable[member.member_path] = member
        else:
            yield member
    if unreadable and find_sevenzip() is None:
        raise MissingDependencyError(
            f"{len(unreadable):,} zip member(s) use a method only 7zz reads (AES, deflate64, ...): "
            f"they need {SEVENZIP_NEEDED}"
        )
    if unreadable:
        for member in _sevenzip(
            path, store, limits, skip=skip, on_progress=on_progress, passwords=passwords, only=unreadable.__contains__
        ):
            unreadable.pop(member.member_path, None)
            yield member
        yield from unreadable.values()  # 7zz didn't list them under the same name
