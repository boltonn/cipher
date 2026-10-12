"""zip and tar (plain or single-stream compressed) with the standard library, in-process.

Container parsing is memory-safe Python; only zlib/bz2/lzma (and the optional zstd/lz4) are C.
Everything streams in `CHUNK_SIZE` pieces, so memory stays flat whatever the member size, and
tar's member list is cleared as it goes so millions of entries don't accumulate.
"""

import errno
import lzma
import stat
import tarfile
import zipfile
import zlib
from collections.abc import Callable, Iterable, Iterator, Sequence
from datetime import UTC, datetime
from functools import partial
from operator import attrgetter
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from filetyper.compression import DECODERS

from cipher.schemas.ingestion.file import Compression
from cipher.utils.output import CHUNK_SIZE, OutputStore, StoredFile
from cipher.utils.uri import Uri
from pyarchive.guard import CountingReader, Guard
from pyarchive.names import MemberNames
from pyarchive.schemas import (
    ArchiveCorruptError,
    ArchiveLimit,
    ArchiveLimitError,
    ArchiveLimits,
    ArchiveProgress,
    ExtractedMember,
    MemberSkipReason,
    MissingDependencyError,
)

ZIP_METHODS = frozenset({zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED, zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA})
ZIP_UTF8_FLAG = 0x800
ZIP_ENCRYPTED_FLAG = 0x1
STREAM_ERRORS = (EOFError, OSError, zlib.error, lzma.LZMAError, tarfile.TarError, zipfile.BadZipFile)

_DECODER_BY_ENCODING = {encoding: open_decoded for encoding, open_decoded in DECODERS.values()}


def copy_to_store(source: BinaryIO, store: OutputStore, guard: Guard) -> StoredFile:
    """Stream `source` into the store under the guard; a raised limit or read error discards the partial file."""
    return write_chunks(iter(partial(source.read, CHUNK_SIZE), b""), store, guard)


def write_chunks(chunks: Iterable[bytes], store: OutputStore, guard: Guard) -> StoredFile:
    """`copy_to_store` for content that arrives as chunks rather than a readable stream."""
    with store.writer() as writer:
        for chunk in chunks:
            try:
                writer.write(chunk)
            except OSError as e:
                if e.errno == errno.ENOSPC:
                    raise ArchiveLimitError(ArchiveLimit.DISK, "output store disk is full") from e
                raise
            guard.wrote(len(chunk))
        return writer.commit()


def open_decoded(raw: BinaryIO, compression: Compression | None) -> BinaryIO:
    """`raw` decoded through its single-stream compression (`raw` itself when uncompressed)."""
    if compression is None:
        return raw
    if (decoder := _DECODER_BY_ENCODING.get(compression)) is None:
        raise MissingDependencyError(f"{compression} needs its decoder: install the `{compression}` extra")
    return decoder(raw)


def iter_zip(
    path: Path | Uri,
    store: OutputStore,
    limits: ArchiveLimits,
    skip: Callable[[str], bool] | None = None,
    on_progress: Callable[[ArchiveProgress], None] | None = None,
    passwords: Sequence[str] = (),
) -> Iterator[ExtractedMember]:
    """Every regular member of a zip, in on-disk order. A corrupt member is reported and the rest still read.

    An encrypted member is tried with each of `passwords`; one none opens is reported `encrypted`.
    """
    with path.open("rb") as f:
        raw = CountingReader(f)
        progress = ArchiveProgress(bytes_in_total=path.stat().st_size)
        guard = Guard(limits, store.scratch_dir, raw, progress, on_progress)
        guard.check_entries(_zip_declared_entries(raw))
        try:
            archive = zipfile.ZipFile(raw)  # noqa: SIM115 -- closed in finally (raw is ours)
        except STREAM_ERRORS as e:
            raise ArchiveCorruptError(f"unreadable zip: {e}") from e
        try:
            infos = sorted((info for info in archive.infolist() if not info.is_dir()), key=attrgetter("header_offset"))
            progress.members_total = len(infos)
            names = MemberNames()
            for info in infos:
                yield _zip_member(archive, info, names, store, guard, skip, passwords)
                guard.finish_member()
        finally:
            archive.close()
            guard.report(force=True)


def _zip_declared_entries(raw: CountingReader) -> int:
    """Entry count from the end-of-central-directory record, read before zipfile loads every entry into memory."""
    endrec = zipfile._EndRecData(raw)  # noqa: SLF001 -- the stdlib's own EOCD reader (zip64-aware)
    raw.seek(0)
    if not endrec:
        raise ArchiveCorruptError("no zip end-of-central-directory record")
    return endrec[zipfile._ECD_ENTRIES_TOTAL]  # noqa: SLF001


def _zip_member(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    names: MemberNames,
    store: OutputStore,
    guard: Guard,
    skip: Callable[[str], bool] | None,
    passwords: Sequence[str],
) -> ExtractedMember:
    member_path = names.claim(_zip_name(info))
    member = ExtractedMember(
        member_path=member_path,
        filename=PurePosixPath(member_path).name,
        declared_size=info.file_size,
        date_last_updated=_zip_mtime(info),
    )
    mode = info.external_attr >> 16
    if stat.S_ISLNK(mode):
        member.skip_reason = MemberSkipReason.LINK
    elif stat.S_IFMT(mode) and not stat.S_ISREG(mode):
        member.skip_reason = MemberSkipReason.SPECIAL
    elif info.compress_type not in ZIP_METHODS:  # deflate64, ppmd, zstd, AES (99): `extract` hands these to 7zz
        member.is_encrypted = bool(info.flag_bits & ZIP_ENCRYPTED_FLAG)
        member.skip_reason = MemberSkipReason.UNSUPPORTED_METHOD
    elif skip is not None and skip(member_path):
        member.skip_reason = MemberSkipReason.ALREADY_DONE
    elif info.flag_bits & ZIP_ENCRYPTED_FLAG:
        member.is_encrypted = True
        member.skip_reason = MemberSkipReason.ENCRYPTED
        for password in passwords:  # ZipCrypto; a wrong one fails its check byte or, 1 time in 256, the CRC
            guard.start_member(declared_size=info.file_size)
            try:
                with archive.open(info, pwd=password.encode()) as source:
                    member.stored = copy_to_store(source, store, guard)
            except (*STREAM_ERRORS, RuntimeError):
                continue
            member.skip_reason = None
            break
    else:
        guard.start_member(declared_size=info.file_size)
        try:
            with archive.open(info) as source:
                member.stored = copy_to_store(source, store, guard)
        except (*STREAM_ERRORS, NotImplementedError, RuntimeError) as e:
            member.skip_reason, member.error = MemberSkipReason.CORRUPT, f"{type(e).__name__}: {e}"
    return member


def _zip_name(info: zipfile.ZipInfo) -> str:
    """Member name; many tools write UTF-8 without setting the flag, so zipfile's cp437 reading is retried as UTF-8."""
    if info.flag_bits & ZIP_UTF8_FLAG:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return info.filename


def _zip_mtime(info: zipfile.ZipInfo) -> datetime | None:
    try:
        return datetime(*info.date_time)
    except ValueError:
        return None


def iter_tar(
    path: Path | Uri,
    store: OutputStore,
    limits: ArchiveLimits,
    compression: Compression | None = None,
    skip: Callable[[str], bool] | None = None,
    on_progress: Callable[[ArchiveProgress], None] | None = None,
) -> Iterator[ExtractedMember]:
    """Every regular member of a tar, streamed (one sequential pass; works for .tar.gz/.xz/.bz2/.zst).

    Raises:
        ArchiveCorruptError: The stream is truncated or unreadable; members before that point were yielded.
    """
    with path.open("rb") as f:
        raw = CountingReader(f)
        progress = ArchiveProgress(bytes_in_total=path.stat().st_size)
        guard = Guard(limits, store.scratch_dir, raw, progress, on_progress)
        names = MemberNames()
        try:
            with open_decoded(raw, compression) as stream, tarfile.open(fileobj=stream, mode="r|") as archive:
                while (info := archive.next()) is not None:
                    archive.members.clear()
                    if info.isdir():
                        continue
                    guard.check_entries(progress.members_done + 1)
                    yield _tar_member(archive, info, names, store, guard, skip)
                    guard.finish_member()
        except STREAM_ERRORS as e:
            raise ArchiveCorruptError(
                f"unreadable past member {progress.members_done:,}: {type(e).__name__}: {e}"
            ) from e
        finally:
            guard.report(force=True)


def _tar_member(
    archive: tarfile.TarFile,
    info: tarfile.TarInfo,
    names: MemberNames,
    store: OutputStore,
    guard: Guard,
    skip: Callable[[str], bool] | None,
) -> ExtractedMember:
    member_path = names.claim(info.name)
    member = ExtractedMember(
        member_path=member_path,
        filename=PurePosixPath(member_path).name,
        declared_size=info.size,
        date_last_updated=datetime.fromtimestamp(info.mtime, tz=UTC) if info.mtime else None,
    )
    if info.issym() or info.islnk():
        member.skip_reason = MemberSkipReason.LINK
    elif not info.isreg():
        member.skip_reason = MemberSkipReason.SPECIAL
    elif skip is not None and skip(member_path):
        member.skip_reason = MemberSkipReason.ALREADY_DONE
    else:
        guard.start_member(declared_size=info.size)
        source = archive.extractfile(info)
        member.stored = copy_to_store(source, store, guard)
    return member


def decode_to_store(
    path: Path | Uri,
    compression: Compression,
    store: OutputStore,
    limits: ArchiveLimits,
    on_progress: Callable[[ArchiveProgress], None] | None = None,
) -> StoredFile:
    """Decode a single-stream compressed file (`report.csv.gz`) into the store, under the same limits.

    Raises:
        ArchiveCorruptError: The stream is truncated or unreadable (nothing is stored).
    """
    with path.open("rb") as f:
        raw = CountingReader(f)
        progress = ArchiveProgress(members_total=1, bytes_in_total=path.stat().st_size)
        guard = Guard(limits, store.scratch_dir, raw, progress, on_progress)
        guard.start_member()
        try:
            with open_decoded(raw, compression) as stream:
                stored = copy_to_store(stream, store, guard)
        except STREAM_ERRORS as e:
            raise ArchiveCorruptError(f"unreadable {compression} stream: {type(e).__name__}: {e}") from e
        guard.finish_member()
        guard.report(force=True)
        return stored
