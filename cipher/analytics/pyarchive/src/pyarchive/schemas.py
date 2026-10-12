from datetime import datetime

from pydantic import Field

from cipher.schemas._base.base import BaseModel, StrEnum
from cipher.schemas.ingestion.file import ArchiveSandbox
from cipher.utils.output import StoredFile

MIB = 1 << 20
GIB = 1 << 30


class ArchiveLimits(BaseModel):
    """Guards against bombs and full disks, all measured on bytes actually written (headers lie)."""

    max_archive_bytes: int | None = Field(
        default=None,
        description="Don't open archives bigger than this. None: PYARCHIVE_MAX_ARCHIVE_GIB if set, else no "
        "limit for a local file and 50 GiB for a remote one (7z / rar / iso are copied locally first)",
    )
    max_total_bytes: int = Field(default=20 * GIB, description="Most bytes one archive may write")
    max_member_bytes: int = Field(default=8 * GIB, description="Most bytes one member may write")
    max_ratio: float = Field(default=250.0, description="Most bytes written per compressed byte read, per member")
    ratio_min_bytes: int = Field(
        default=64 * MIB, description="Ratio only applies past this many bytes (text and sparse files compress hard)"
    )
    max_entries: int = Field(default=1_000_000, description="Most members one archive may list")
    min_free_bytes: int = Field(default=10 * GIB, description="Stop when the output store's disk has less free than this")
    disk_check_bytes: int = Field(default=256 * MIB, description="How often (in bytes written) free disk is re-checked")
    max_memory_bytes: int = Field(default=16 * GIB, description="Address-space cap for a sandboxed decoder (7zz)")
    sandbox: ArchiveSandbox = Field(
        default=ArchiveSandbox.BEST_EFFORT,
        description="How 7zz is confined: best effort, required (every layer, else fail), or off",
    )


class ArchiveLimit(StrEnum):
    """Which limit stopped an extraction."""

    ARCHIVE_BYTES = "archive_bytes"
    TOTAL_BYTES = "total_bytes"
    MEMBER_BYTES = "member_bytes"
    RATIO = "ratio"
    ENTRIES = "entries"
    DISK = "disk"


class MemberSkipReason(StrEnum):
    """Why a member was listed but not written."""

    ALREADY_DONE = "already_done"
    ENCRYPTED = "encrypted"
    LINK = "link"
    SPECIAL = "special"
    UNSUPPORTED_METHOD = "unsupported_method"
    CORRUPT = "corrupt"


class ExtractedMember(BaseModel):
    """One archive member: written to the output store, or skipped with a reason."""

    member_path: str = Field(description="Normalized path inside the archive, unique within it (display only)")
    filename: str = Field(description="Basename of the member")
    stored: StoredFile | None = Field(default=None, description="Where the content went; None when skipped")
    is_encrypted: bool = Field(
        default=False, description="Encrypted in the archive (its stored file, when there is one, is the decrypted content)"
    )
    skip_reason: MemberSkipReason | None = Field(default=None)
    error: str | None = Field(default=None, description="What went wrong, for a corrupt member")
    declared_size: int | None = Field(default=None, description="Size the archive's header claims")
    date_last_updated: datetime | None = Field(default=None)
    date_created: datetime | None = Field(default=None)


class ArchiveProgress(BaseModel):
    """Progress inside one archive (reported throttled; never on the per-chunk hot path)."""

    members_done: int = Field(default=0)
    members_total: int | None = Field(default=None, description="Known for zip; None for streamed tar")
    bytes_in: int = Field(default=0, description="Compressed bytes of the archive read so far")
    bytes_in_total: int = Field(default=0, description="Size of the archive")
    bytes_out: int = Field(default=0, description="Bytes written so far")


class ArchiveError(Exception):
    """Base for extraction failures; members yielded before it are real and kept."""


class ArchiveLimitError(ArchiveError):
    """A limit tripped; the member in flight was discarded."""

    def __init__(self, limit: ArchiveLimit, detail: str) -> None:
        super().__init__(f"limit:{limit.value} {detail}")
        self.limit = limit


class ArchiveCorruptError(ArchiveError):
    """The archive is truncated or unreadable past some point."""


class ArchiveEncryptedError(ArchiveError):
    """The archive's own listing is encrypted (7z `-mhe`, rar `-hp`): nothing can be read without a password."""


class SandboxUnavailableError(ArchiveError):
    """The sandbox is `required` and a layer of it could not be applied here."""


class MissingDependencyError(ArchiveError):
    """A tool this archive needs isn't installed; the message says what to install."""


class UnsupportedArchiveError(ArchiveError):
    """No installed backend reads this filetype."""
