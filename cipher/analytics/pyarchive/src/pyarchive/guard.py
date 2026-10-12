"""Limit accounting and throttled progress for one archive."""

import shutil
import time
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO

from pyarchive.schemas import ArchiveLimit, ArchiveLimitError, ArchiveLimits, ArchiveProgress

PROGRESS_INTERVAL_SECONDS = 0.5


class CountingReader:
    """Wraps the raw archive file, counting compressed bytes read (for the ratio guard and progress)."""

    def __init__(self, raw: BinaryIO) -> None:
        self._raw = raw
        self.bytes_read = 0

    def read(self, size: int = -1) -> bytes:
        """Read and count."""
        data = self._raw.read(size)
        self.bytes_read += len(data)
        return data

    def readinto(self, buffer: bytearray | memoryview) -> int:
        """Read into a buffer and count."""
        n = self._raw.readinto(buffer)
        self.bytes_read += n or 0
        return n

    def seek(self, offset: int, whence: int = 0) -> int:
        """Delegate."""
        return self._raw.seek(offset, whence)

    def tell(self) -> int:
        """Delegate."""
        return self._raw.tell()

    def seekable(self) -> bool:
        """Delegate."""
        return self._raw.seekable()

    def readable(self) -> bool:
        """Always readable."""
        return True

    @property
    def closed(self) -> bool:
        """Delegate."""
        return self._raw.closed

    def __enter__(self) -> "CountingReader":
        """Usable where a decoder stream would be; closing stays with whoever opened the raw file."""
        return self

    def __exit__(self, *_: object) -> None:
        """Leave the raw file open for its owner."""


class Guard:
    """Counts what one archive writes and raises `ArchiveLimitError` the moment a limit is crossed."""

    def __init__(
        self,
        limits: ArchiveLimits,
        disk_root: Path,
        raw: CountingReader,
        progress: ArchiveProgress,
        on_progress: Callable[[ArchiveProgress], None] | None = None,
    ) -> None:
        self.limits = limits
        self.disk_root = disk_root
        self.raw = raw
        self.progress = progress
        self.on_progress = on_progress
        self._member_out = 0
        self._member_in_start = 0
        self._next_disk_check = 0
        self._last_report = 0.0

    def check_entries(self, count: int) -> None:
        """Refuse an archive that lists more members than allowed."""
        if count > self.limits.max_entries:
            raise ArchiveLimitError(ArchiveLimit.ENTRIES, f"{count:,} members > {self.limits.max_entries:,}")

    def start_member(self, declared_size: int | None = None) -> None:
        """Reset per-member counters; refuse up front a member the disk can't hold."""
        self._member_out = 0
        self._member_in_start = self.raw.bytes_read
        if declared_size:
            self._check_disk(need=declared_size)

    def wrote(self, n: int) -> None:
        """Account for `n` bytes written by the member in flight."""
        self._member_out += n
        self.progress.bytes_out += n
        limits = self.limits
        if self.progress.bytes_out > limits.max_total_bytes:
            raise ArchiveLimitError(ArchiveLimit.TOTAL_BYTES, f"archive wrote > {limits.max_total_bytes:,} bytes")
        if self._member_out > limits.max_member_bytes:
            raise ArchiveLimitError(ArchiveLimit.MEMBER_BYTES, f"member wrote > {limits.max_member_bytes:,} bytes")
        if self._member_out > limits.ratio_min_bytes:
            read = max(self.raw.bytes_read - self._member_in_start, 1)
            if self._member_out / read > limits.max_ratio:
                raise ArchiveLimitError(
                    ArchiveLimit.RATIO, f"member wrote {self._member_out:,} bytes from {read:,} compressed"
                )
        if self.progress.bytes_out >= self._next_disk_check:
            self._check_disk()
        self.report()

    def finish_member(self) -> None:
        """Count a member as done (written or skipped)."""
        self.progress.members_done += 1
        self.report()

    def report(self, force: bool = False) -> None:
        """Call `on_progress`, at most every `PROGRESS_INTERVAL_SECONDS` unless forced."""
        now = time.monotonic()
        if self.on_progress is None or (not force and now - self._last_report < PROGRESS_INTERVAL_SECONDS):
            return
        self._last_report = now
        self.progress.bytes_in = self.raw.tell()
        self.on_progress(self.progress.model_copy())

    def _check_disk(self, need: int = 0) -> None:
        self._next_disk_check = self.progress.bytes_out + self.limits.disk_check_bytes
        free = shutil.disk_usage(self.disk_root).free
        if free - need < self.limits.min_free_bytes:
            raise ArchiveLimitError(
                ArchiveLimit.DISK, f"{free:,} bytes free, need {need:,} + {self.limits.min_free_bytes:,} reserve"
            )
