"""mbox mail folders (Thunderbird, Apple Mail, Gmail Takeout, Unix mail): one `.eml` member per message.

Streamed line by line, so a mailbox of any size reads in flat memory. A message starts at a
`From <sender> <asctime>` separator line, which is dropped; mboxrd's `>From ` escaping is undone.
Members are named by subject (`~2` for a repeat), so a re-run names them the same and can resume.
"""

import re
from collections.abc import Callable, Iterator
from email.header import decode_header, make_header
from email.parser import BytesHeaderParser
from itertools import chain
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from filetyper.models.magic import MBOX_FROM_LINE

from cipher.schemas.ingestion.file import Compression
from cipher.utils.output import CHUNK_SIZE, OutputStore
from cipher.utils.uri import Uri
from pyarchive.backends.stdlib import STREAM_ERRORS, open_decoded, write_chunks
from pyarchive.guard import CountingReader, Guard
from pyarchive.names import MemberNames
from pyarchive.schemas import ArchiveCorruptError, ArchiveLimits, ArchiveProgress, ExtractedMember, MemberSkipReason

_ESCAPED_FROM = re.compile(rb"^>(>*From )")
_BLANK_LINES = frozenset({b"\n", b"\r\n"})
_MAX_LINE_BYTES = 16 * CHUNK_SIZE
_MAX_HEADER_BYTES = 1 << 20
_MAX_NAME_CHARS = 120


def iter_mbox(
    path: Path | Uri,
    store: OutputStore,
    limits: ArchiveLimits,
    compression: Compression | None = None,
    skip: Callable[[str], bool] | None = None,
    on_progress: Callable[[ArchiveProgress], None] | None = None,
) -> Iterator[ExtractedMember]:
    """Every message of an mbox (plain or single-stream compressed) as an `.eml` member.

    Raises:
        ArchiveCorruptError: The stream is unreadable; messages before that point were yielded.
    """
    with path.open("rb") as f:
        raw = CountingReader(f)
        progress = ArchiveProgress(bytes_in_total=path.stat().st_size)
        guard = Guard(limits, store.scratch_dir, raw, progress, on_progress)
        names = MemberNames()
        try:
            with open_decoded(raw, compression) as stream:
                for message in _messages(_lines(stream)):
                    guard.check_entries(progress.members_done + 1)
                    yield _member(message, names, store, guard, skip)
                    for _ in message:  # a skipped message is read past
                        pass
                    guard.finish_member()
        except STREAM_ERRORS as e:
            raise ArchiveCorruptError(f"unreadable past message {progress.members_done:,}: {e}") from e
        finally:
            guard.report(force=True)


def _lines(stream: BinaryIO) -> Iterator[bytes]:
    """Lines with their endings; an endless line is cut so memory stays bounded."""
    tail = b""
    while chunk := stream.read(CHUNK_SIZE):
        *lines, tail = (tail + chunk).split(b"\n")
        yield from (line + b"\n" for line in lines)
        if len(tail) > _MAX_LINE_BYTES:
            yield tail
            tail = b""
    if tail:
        yield tail


def _messages(lines: Iterator[bytes]) -> Iterator[Iterator[bytes]]:
    """Each message's lines (unescaped, separator dropped); one must be read through before the next."""
    separator = next((line for line in lines if MBOX_FROM_LINE.match(line)), None)
    while separator is not None:
        separator = None

        def body() -> Iterator[bytes]:
            nonlocal separator
            for line in lines:
                if MBOX_FROM_LINE.match(line):
                    separator = line
                    return
                yield _ESCAPED_FROM.sub(rb"\1", line)

        yield body()


def _member(
    message: Iterator[bytes],
    names: MemberNames,
    store: OutputStore,
    guard: Guard,
    skip: Callable[[str], bool] | None,
) -> ExtractedMember:
    header = bytearray()
    for line in message:
        header += line
        if line in _BLANK_LINES or len(header) > _MAX_HEADER_BYTES:
            break
    member_path = names.claim(_name(bytes(header)))
    member = ExtractedMember(member_path=member_path, filename=PurePosixPath(member_path).name)
    if skip is not None and skip(member_path):
        member.skip_reason = MemberSkipReason.ALREADY_DONE
        return member
    guard.start_member()
    member.stored = write_chunks(_rechunk(chain([bytes(header)], message)), store, guard)
    return member


def _rechunk(lines: Iterator[bytes]) -> Iterator[bytes]:
    buffer = bytearray()
    for line in lines:
        buffer += line
        if len(buffer) >= CHUNK_SIZE:
            yield bytes(buffer)
            buffer.clear()
    if buffer:
        yield bytes(buffer)


def _name(header: bytes) -> str:
    """`<subject>.eml`, made safe as one path part."""
    raw = BytesHeaderParser().parsebytes(header).get("subject") or ""
    try:
        subject = str(make_header(decode_header(raw)))
    except (UnicodeDecodeError, LookupError, ValueError):
        subject = str(raw)
    subject = " ".join(re.sub(r"[/\\]", "_", subject).split())[:_MAX_NAME_CHARS]
    return f"{subject or 'message'}.eml"
