"""Seeing through single-stream compression: `report.csv.gz` is typed as the csv inside it.

Compression is an encoding of one file, never a container, so a compressed file is typed by the
first bytes of its decoded content and carries a `CompressionInfo` saying how it was found.
"""

import bz2
import gzip
import lzma
import struct
from collections.abc import Callable
from datetime import UTC, datetime
from typing import BinaryIO

from cipher.schemas.ingestion.file import Compression

PEEK_BYTES = 64 * 1024
TAR_MAGIC_OFFSET = 257

DECODERS: dict[str, tuple[Compression, Callable[[BinaryIO], BinaryIO]]] = {
    "gzip": (Compression.GZIP, gzip.open),
    "bzip": (Compression.BZIP2, bz2.open),
    "xz": (Compression.XZ, lzma.open),
}
try:
    from compression import zstd  # Python 3.14+
except ImportError:
    try:
        from backports import zstd
    except ImportError:
        zstd = None
if zstd is not None:
    DECODERS["zst"] = (Compression.ZSTD, zstd.open)
try:
    import lz4.frame

    DECODERS["lz4"] = (Compression.LZ4, lz4.frame.open)
except ImportError:
    pass

# Filetypes whose decoder isn't installed here -> what to install (the `zstd` / `lz4` extras).
MISSING_DECODERS: dict[str, str] = {
    filetype: need
    for filetype, need in (
        ("zst", "the zstd decoder: install the `zstd` extra (backports.zstd; built in from Python 3.14)"),
        ("lz4", "the lz4 decoder: install the `lz4` extra (lz4)"),
    )
    if filetype not in DECODERS
}


def peek_decoded(raw: BinaryIO, filetype: str) -> tuple[Compression, bytes] | None:
    """The encoding and first decoded bytes of a compressed file; None if not compressed or not decodable here.

    Args:
        raw: The file as found, positioned at its start.
        filetype: Its filetype as typed from the raw bytes (e.g. `gzip`).

    Returns:
        `(encoding, head)` with up to `PEEK_BYTES` of decoded content, or None.
    """
    if (decoder := DECODERS.get(filetype)) is None:
        return None
    encoding, open_decoded = decoder
    try:
        with open_decoded(raw) as decoded:
            return encoding, decoded.read(PEEK_BYTES)
    except (OSError, EOFError, lzma.LZMAError, ValueError):
        return None


def is_tar(head: bytes) -> bool:
    """True when decoded content starts with a POSIX/GNU tar header."""
    return head[TAR_MAGIC_OFFSET : TAR_MAGIC_OFFSET + 5] == b"ustar"


def gzip_header(head: bytes) -> tuple[str | None, datetime | None]:
    """The original filename and modified time a gzip header stores (RFC 1952), when present.

    Args:
        head: The first bytes of the file as found (the header fits well within 64 KiB).
    """
    if len(head) < 10 or head[:2] != b"\x1f\x8b":
        return None, None
    flags, mtime = head[3], struct.unpack("<I", head[4:8])[0]
    date_modified = datetime.fromtimestamp(mtime, tz=UTC) if mtime else None
    if not flags & 0x08:
        return None, date_modified
    start = 10
    if flags & 0x04:
        start += 2 + struct.unpack("<H", head[10:12])[0]
    end = head.find(b"\x00", start)
    filename = head[start:end].decode("latin-1") if end > start else None
    return filename, date_modified
