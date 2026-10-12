"""7z, rar, iso, cab and the rest through the official 7-Zip (`7zz`), always inside `pyarchive.jail`.

`7zz` is optional: without it these filetypes fail with what to install (`SEVENZIP_NEEDED`). It is
found at `SEVENZIP_PATH`, else `7zz` on `PATH`, else `~/.local/share/cipher/bin/7zz`; use the
static build (`7zzs` in the release) so the sandbox only has to let one file execute.

Members stream: `7zz x -bb1` prints `- <path>` as each file starts, so the previous one is done
and moves into the output store (a rename: the scratch dir sits inside the store) while the next
decodes. Encrypted members get a pass per known password; a password goes to 7zz on stdin. A watcher kills `7zz` when the archive writes too much, expands too far past its own
size, or the disk runs low; `RLIMIT_FSIZE` stops any one file at the member limit.
"""

import os
import shutil
import subprocess
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable, Generator, Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from functools import cache
from pathlib import Path, PurePosixPath
from tempfile import mkdtemp

from loguru import logger

from cipher.schemas.ingestion.file import ArchiveSandbox
from cipher.utils.output import OutputStore
from pyarchive import jail
from pyarchive.names import MemberNames
from pyarchive.schemas import (
    ArchiveCorruptError,
    ArchiveEncryptedError,
    ArchiveLimit,
    ArchiveLimitError,
    ArchiveLimits,
    ArchiveProgress,
    ExtractedMember,
    MemberSkipReason,
    SandboxUnavailableError,
)

SEVENZIP_FILETYPES = frozenset({"sevenzip", "rar", "iso", "cab", "arj", "lha", "xar", "dmg", "squashfs"})
DEFAULT_SEVENZIP = Path("~/.local/share/cipher/bin/7zz")
WATCH_SECONDS = 0.5
THREADS = os.cpu_count() or 4  # 7zz can't see /proc in the jail, so it is told
# Read-only extras the jail lets 7zz see: locale data, so member names decode as UTF-8.
SYSTEM_READ = tuple(path for path in ("/usr/lib/locale",) if os.path.isdir(path))
SIGXFSZ_EXIT = -25
SEVENZIP_NEEDED = (
    "7-Zip's `7zz`: put the static `7zzs` from https://github.com/ip7z/7zip/releases at "
    "~/.local/share/cipher/bin/7zz (chmod +x), or set SEVENZIP_PATH"
)


@cache
def find_sevenzip() -> Path | None:
    """The `7zz` binary to use, or None when there isn't one (7z / rar / iso are then unsupported)."""
    for candidate in (os.environ.get("SEVENZIP_PATH"), shutil.which("7zz"), str(DEFAULT_SEVENZIP.expanduser())):
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return Path(candidate).resolve()
    return None


@dataclass
class _Listed:
    path: str
    is_dir: bool
    is_link: bool
    is_encrypted: bool
    size: int | None
    modified: datetime | None
    created: datetime | None


def _jailed(binary: Path, args: list[str], archive: Path, scratch: Path, limits: ArchiveLimits) -> subprocess.Popen:
    """Start `7zz <args>` in the jail (or bare, with the sandbox off); checks (and logs) which layers applied."""
    pipes = {"stdin": subprocess.PIPE, "stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "cwd": scratch}
    if limits.sandbox == ArchiveSandbox.OFF:
        _warn_once(("off",), "7-Zip runs without its sandbox (--sandbox off): no network block or file access limits")
        return subprocess.Popen([str(binary), *args], env={"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}, **pipes)  # noqa: S603
    report_read, report_write = os.pipe()
    command = jail.jail_command(
        [str(binary), *args],
        read=[str(archive), *SYSTEM_READ],
        execute=[str(binary)],
        write=[str(scratch)],
        max_file_bytes=limits.max_member_bytes,
        max_memory_bytes=limits.max_memory_bytes,
        report_fd=report_write,
    )
    process = subprocess.Popen(command, pass_fds=(report_write,), **pipes)  # noqa: S603 -- fixed argv, no shell
    os.close(report_write)
    with os.fdopen(report_read) as report:
        outcome = report.read()
    _check_sandbox(outcome, limits, process)
    return process


def _check_sandbox(outcome: str, limits: ArchiveLimits, process: subprocess.Popen) -> None:
    import json

    layers = json.loads(outcome) if outcome else {layer: "no report" for layer in jail.LAYERS}
    missing = {layer: why for layer, why in layers.items() if why != "ok"}
    detail = jail.explain(missing)
    if missing and limits.sandbox == ArchiveSandbox.REQUIRED:
        process.kill()
        raise SandboxUnavailableError(f"--sandbox required, but part of it can't apply here. {detail}")
    if missing:
        _warn_once(
            tuple(sorted(missing)),
            f"7-Zip (for 7z / rar / iso) is running with only part of its sandbox. {detail} "
            "Or pass --sandbox off to run without the sandbox and hide this, or --sandbox required to stop instead.",
        )


@cache
def _warn_once(_key: tuple, detail: str) -> None:
    logger.warning(detail)


def list_members(
    binary: Path, path: Path, scratch: Path, limits: ArchiveLimits, passwords: Sequence[str] = ()
) -> tuple[list[_Listed], str | None]:
    """Every entry of the archive (`7zz l -slt`), and the password that opened an encrypted listing.

    Raises:
        ArchiveEncryptedError: The listing is encrypted and no password opens it.
        ArchiveCorruptError: 7zz can't open it.
    """
    for password in (None, *passwords):
        process = _jailed(
            binary, ["l", "-slt", "-sccUTF-8", *_password_args(password), str(path)], path, scratch, limits
        )
        out, err = process.communicate(_password_input(password))
        text = out.decode("utf-8", errors="replace")
        if "Cannot open encrypted archive" in text + err.decode("utf-8", errors="replace"):
            continue
        if process.returncode != 0 or "\n----------\n" not in text:
            raise ArchiveCorruptError(f"7zz can't list it (exit {process.returncode}): {_last_error(text, err)}")
        blocks = text.split("\n----------\n", 1)[1].split("\n\n")
        return [_parse_entry(block) for block in blocks if "Path = " in block], password
    raise ArchiveEncryptedError(f"the archive's listing is encrypted ({len(passwords)} known password(s) tried)")


def _password_args(password: str | None) -> list[str]:
    """No password: `-p-` (never prompt). A password goes on stdin, never the command line (other users see that)."""
    return ["-p-"] if password is None else []


def _password_input(password: str | None) -> bytes | None:
    return None if password is None else f"{password}\n".encode()


def _parse_entry(block: str) -> _Listed:
    fields = dict(line.split(" = ", 1) for line in block.splitlines() if " = " in line)
    attributes = fields.get("Attributes", "")
    mode = attributes.split()[-1] if attributes.split() else ""
    return _Listed(
        path=fields["Path"],
        is_dir=fields.get("Folder") == "+" or attributes.startswith("D") or mode.startswith("d"),
        is_link=mode.startswith("l") or any(fields.get(key) for key in ("Symbolic Link", "Hard Link", "Copy Link")),
        is_encrypted=fields.get("Encrypted") == "+",
        size=int(fields["Size"]) if fields.get("Size", "").isdigit() else None,
        modified=_time(fields.get("Modified")),
        created=_time(fields.get("Created")),
    )


def _time(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value[:26]) if value else None
    except ValueError:
        return None


def _last_error(out: str, err: bytes) -> str:
    lines = [
        line
        for line in (out + err.decode("utf-8", errors="replace")).splitlines()
        if "ERROR" in line or "Error" in line
    ]
    return lines[-1].strip() if lines else "no detail"


class _Watch(threading.Thread):
    """Kills 7zz when the archive writes too much, expands too far, or the disk runs low."""

    def __init__(
        self, process: subprocess.Popen, store_root: Path, archive_size: int, limits: ArchiveLimits, written: int = 0
    ) -> None:
        super().__init__(daemon=True)
        self.process, self.store_root, self.archive_size, self.limits = process, store_root, archive_size, limits
        self.written = written
        self.in_flight: Path | None = None
        self.tripped: ArchiveLimitError | None = None

    def run(self) -> None:
        """Poll until 7zz exits."""
        while self.process.poll() is None:
            if (error := self.check()) is not None:
                self.tripped = error
                self.process.kill()
                return
            time.sleep(WATCH_SECONDS)

    def check(self) -> ArchiveLimitError | None:
        """The limit the archive has crossed so far, if any."""
        limits = self.limits
        current = self.in_flight.stat().st_size if self.in_flight and self.in_flight.exists() else 0
        total = self.written + current
        if current > limits.max_member_bytes:  # RLIMIT_FSIZE stops it in the jail; this holds with the sandbox off
            return ArchiveLimitError(ArchiveLimit.MEMBER_BYTES, f"a member passed {limits.max_member_bytes:,} bytes")
        if total > limits.max_total_bytes:
            return ArchiveLimitError(ArchiveLimit.TOTAL_BYTES, f"archive wrote > {limits.max_total_bytes:,} bytes")
        if total > limits.ratio_min_bytes and total / max(self.archive_size, 1) > limits.max_ratio:
            return ArchiveLimitError(ArchiveLimit.RATIO, f"archive wrote {total:,} bytes from {self.archive_size:,}")
        if (free := shutil.disk_usage(self.store_root).free) < limits.min_free_bytes:
            return ArchiveLimitError(ArchiveLimit.DISK, f"{free:,} bytes free < {limits.min_free_bytes:,} reserve")
        return None


def iter_sevenzip(
    path: Path,
    store: OutputStore,
    limits: ArchiveLimits,
    skip: Callable[[str], bool] | None = None,
    on_progress: Callable[[ArchiveProgress], None] | None = None,
    binary: Path | None = None,
    *,
    passwords: Sequence[str] = (),
    only: Callable[[str], bool] | None = None,
) -> Iterator[ExtractedMember]:
    """Every regular member of an archive 7zz reads, streamed into the store as 7zz finishes each.

    Plain members come out in one pass; encrypted ones are then tried with each known password in
    turn, and those none opens are reported `encrypted`. Members `skip` names are never extracted.

    Args:
        path: The archive.
        store: Where members go.
        limits: Bomb and disk guards.
        skip: Member paths already recorded (resume).
        on_progress: Throttled progress callback.
        binary: `7zz` (default `find_sevenzip()`).
        passwords: Passwords to try on encrypted members (and an encrypted listing), in order.
        only: Restrict to these member paths (a zip's members the stdlib can't read).

    Raises:
        ArchiveEncryptedError / ArchiveCorruptError / ArchiveLimitError / SandboxUnavailableError
    """
    binary, path = binary or find_sevenzip(), path.resolve()  # the jail runs in the scratch dir
    scratch = Path(mkdtemp(prefix="7zz-", dir=store.scratch_dir))
    try:
        listed, opened_with = list_members(binary, path, scratch, limits, passwords)
        listed = [entry for entry in listed if not entry.is_dir]
        if len(listed) > limits.max_entries:
            raise ArchiveLimitError(ArchiveLimit.ENTRIES, f"{len(listed):,} members > {limits.max_entries:,}")
        names = MemberNames()
        pairs = [(entry, names.claim(entry.path)) for entry in listed]
        if only is not None:
            pairs = [pair for pair in pairs if only(pair[1])]
        run = _Run(path, scratch, store, limits, binary, ArchiveProgress(members_total=len(pairs)), on_progress)
        plain, locked = [], []
        for entry, member_path in pairs:
            if entry.is_link or (skip is not None and skip(member_path)):
                reason = MemberSkipReason.LINK if entry.is_link else MemberSkipReason.ALREADY_DONE
                yield run.done(_member(entry, member_path, skip_reason=reason))
            else:
                (locked if entry.is_encrypted else plain).append((entry, member_path))
        if plain:
            yield from run.extract(plain, password=None, select=len(plain) < len(listed))
        for password in dict.fromkeys(p for p in (opened_with, *passwords) if p is not None):
            if not locked:
                break
            locked = yield from run.extract(locked, password=password, select=True)
        for entry, member_path in locked:
            yield run.done(_member(entry, member_path, skip_reason=MemberSkipReason.ENCRYPTED))
        run.report()
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _member(entry: _Listed, member_path: str, **fields: object) -> ExtractedMember:
    return ExtractedMember(
        member_path=member_path,
        filename=PurePosixPath(member_path).name,
        declared_size=entry.size,
        is_encrypted=entry.is_encrypted,
        date_last_updated=entry.modified,
        date_created=entry.created,
        **fields,
    )


@dataclass
class _Run:
    """One archive's extraction: shared scratch, limits and progress across its passes."""

    path: Path
    scratch: Path
    store: OutputStore
    limits: ArchiveLimits
    binary: Path
    progress: ArchiveProgress
    on_progress: Callable[[ArchiveProgress], None] | None

    def __post_init__(self) -> None:
        self.progress.bytes_in_total = self.path.stat().st_size

    def report(self) -> None:
        """Send the progress so far."""
        if self.on_progress is not None:
            self.on_progress(self.progress.model_copy())

    def done(self, member: ExtractedMember) -> ExtractedMember:
        """Count a member as finished."""
        self.progress.members_done += 1
        return member

    def extract(
        self, pairs: list[tuple[_Listed, str]], *, password: str | None, select: bool
    ) -> Generator[ExtractedMember, None, list[tuple[_Listed, str]]]:
        """One `7zz x` pass over `pairs` (all members unless `select`); returns those the password didn't open.

        With `-bse1` an item's error lines follow its `- <path>` (or `T <path>`: not written) line and
        come before the next item's, so each member is settled when the next one starts.
        """
        out = Path(mkdtemp(prefix="out-", dir=self.scratch))
        by_path: dict[str, deque[tuple[_Listed, str]]] = defaultdict(deque)
        for entry, member_path in pairs:
            by_path[entry.path].append((entry, member_path))
        args = ["x", str(self.path), f"-o{out}", "-y", "-sccUTF-8", "-bb1", "-bso1", "-bse1", "-bsp0"]
        args += [f"-mmt{THREADS}", *_password_args(password)]
        if select:
            listfile = self.scratch / "members.list"
            listfile.write_text("".join(f"{path}\n" for path in by_path if "\n" not in path), encoding="utf-8")
            args += ["-spd", "-scsUTF-8", f"@{listfile}"]
        process = _jailed(self.binary, args, self.path, self.scratch, self.limits)
        if process.stdin is not None:
            process.stdin.write(_password_input(password) or b"")
            process.stdin.close()
        watch = _Watch(process, self.store.scratch_dir, self.progress.bytes_in_total, self.limits, self.progress.bytes_out)
        watch.start()
        locked: list[tuple[_Listed, str]] = []
        current: tuple[str, bool] | None = None  # (path, written)
        error: str | None = None
        stray: list[str] = []

        def settle() -> ExtractedMember | None:
            if current is None or not (queue := by_path.get(current[0])):
                return None
            (entry, member_path), file = queue.popleft(), out / current[0]
            if not queue:
                del by_path[current[0]]
            wrong_password = entry.is_encrypted and (not current[1] or "password" in (error or "").lower())
            if wrong_password or error or not current[1]:
                file.unlink(missing_ok=True)
                if wrong_password:
                    locked.append((entry, member_path))
                    return None
                return self.done(
                    _member(entry, member_path, skip_reason=MemberSkipReason.CORRUPT, error=error or "not written")
                )
            if file.is_symlink() or not file.is_file() or not file.resolve().is_relative_to(out.resolve()):
                return None
            if file.stat().st_size > self.limits.max_member_bytes:  # only reachable with the sandbox off
                file.unlink()
                raise ArchiveLimitError(
                    ArchiveLimit.MEMBER_BYTES, f"a member passed {self.limits.max_member_bytes:,} bytes"
                )
            member = _member(entry, member_path)
            member.stored = self.store.put_file(file, move=True)
            watch.written += member.stored.size
            self.progress.bytes_out = watch.written
            if (tripped := watch.check()) is not None:  # deterministic, not only on the watcher's poll
                raise tripped
            return self.done(member)

        try:
            for raw_line in process.stdout:
                line = raw_line.decode("utf-8", errors="replace").rstrip("\n")
                if line[:2] in ("- ", "T "):
                    if (member := settle()) is not None:
                        self.report()
                        yield member
                    current, error = (line[2:], line[0] == "-"), None
                    watch.in_flight = out / current[0]
                elif line.startswith("ERROR"):
                    if current is not None and line.endswith(f" : {current[0]}"):
                        error = line.removesuffix(f" : {current[0]}").removeprefix("ERROR: ").strip()
                    else:
                        stray.append(line)
            process.wait()
            watch.join()
            if watch.tripped is not None:
                raise watch.tripped
            if process.returncode == SIGXFSZ_EXIT:
                raise ArchiveLimitError(
                    ArchiveLimit.MEMBER_BYTES, f"a member passed {self.limits.max_member_bytes:,} bytes"
                )
            if (member := settle()) is not None:
                yield member
            if process.returncode not in (0, 1) and stray:
                # A wrong password can decode to garbage that also fails the block as a whole
                # (`ERROR: Data Error : #1`, no member named); that's the locked members, not corruption.
                if not locked:
                    raise ArchiveCorruptError(f"7zz exit {process.returncode}: {stray[-1].strip()}")
                logger.debug(f"7zz block errors from a wrong password, ignored: {stray}")
            for entry, member_path in (pair for queue in by_path.values() for pair in queue):
                if entry.is_encrypted:
                    locked.append((entry, member_path))
                else:
                    yield self.done(
                        _member(entry, member_path, skip_reason=MemberSkipReason.CORRUPT, error="not written")
                    )
            return locked
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            shutil.rmtree(out, ignore_errors=True)
