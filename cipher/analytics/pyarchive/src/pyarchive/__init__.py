"""Safe, streaming archive extraction into a content-addressed output store (see docs/archive-extraction.md)."""

from pyarchive.backends.sevenzip import find_sevenzip
from pyarchive.backends.stdlib import decode_to_store
from pyarchive.extract import archive_filetypes, extract, missing_dependency, supported_filetypes
from pyarchive.schemas import (
    ArchiveCorruptError,
    ArchiveEncryptedError,
    ArchiveError,
    ArchiveLimit,
    ArchiveLimitError,
    ArchiveLimits,
    ArchiveProgress,
    ExtractedMember,
    MemberSkipReason,
    MissingDependencyError,
    SandboxUnavailableError,
    UnsupportedArchiveError,
)

__all__ = [
    "ArchiveCorruptError",
    "ArchiveEncryptedError",
    "ArchiveError",
    "ArchiveLimit",
    "ArchiveLimitError",
    "ArchiveLimits",
    "ArchiveProgress",
    "ExtractedMember",
    "MemberSkipReason",
    "MissingDependencyError",
    "SandboxUnavailableError",
    "UnsupportedArchiveError",
    "decode_to_store",
    "extract",
    "find_sevenzip",
    "archive_filetypes",
    "missing_dependency",
    "supported_filetypes",
]
