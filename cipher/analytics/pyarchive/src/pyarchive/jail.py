"""Run an untrusted-input decoder (7zz) boxed in, with nothing to install: `python -I jail.py ... -- cmd`.

Run by file path, never `-m pyarchive.jail`: importing the package loads magika, whose threads
would make the user namespace below impossible (`unshare` refuses a multi-threaded process).
Only the standard library is imported here.

The launcher restricts itself, then `exec`s the command, which inherits every restriction:

1. **rlimits** -- `RLIMIT_FSIZE` (the kernel stops any file growing past the per-member limit),
   `RLIMIT_AS`, `RLIMIT_CORE` 0; `PR_SET_NO_NEW_PRIVS`; a new session; an empty environment.
2. **no network** -- `os.unshare(CLONE_NEWUSER | CLONE_NEWNET)`: a network namespace with no interfaces.
3. **filesystem** -- Landlock (Linux 5.13+, unprivileged): read the archive, run the binary, write
   only the scratch directory; everything else on the box (`.env`, `~/.ssh`, the output store) is
   unreachable.

Each layer is best effort -- an old kernel, Landlock missing from `lsm=`, user namespaces off, a
container's seccomp -- and the launcher reports which it got on `--report-fd`, so the caller can
log it or refuse (`sandbox=required`). Where the jail gets in 7zz's own way, `sandbox=off` runs
7zz directly instead.
"""

import argparse
import ctypes
import json
import os
import resource
import struct
import sys

_SYS_LANDLOCK_CREATE_RULESET, _SYS_LANDLOCK_ADD_RULE, _SYS_LANDLOCK_RESTRICT_SELF = 444, 445, 446
_LANDLOCK_CREATE_RULESET_VERSION = 1
_LANDLOCK_RULE_PATH_BENEATH = 1
_PR_SET_NO_NEW_PRIVS = 38

_EXECUTE, _WRITE_FILE, _READ_FILE, _READ_DIR = 1 << 0, 1 << 1, 1 << 2, 1 << 3
_ABI_ACCESS = {1: (1 << 13) - 1, 2: (1 << 14) - 1, 3: (1 << 15) - 1}  # v2 adds REFER, v3 TRUNCATE
_TRUNCATE = 1 << 14

LAYERS = ("rlimits", "no_network", "filesystem")
# Per layer, in plain words: what it is, what goes unprotected without it, and how to get it.
PLAIN = {
    "rlimits": (
        "resource limits",
        "7-Zip's memory isn't capped, and an oversized file is only caught when it finishes",
        "this is unusual on Linux; ask whoever runs the machine or container about its process limits",
    ),
    "no_network": (
        "network block",
        "7-Zip isn't cut off from the network while it reads archives",
        "an admin can run `sudo sysctl -w kernel.unprivileged_userns_clone=1` and, on Ubuntu 24.04 or newer, "
        "`sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0`",
    ),
    "filesystem": (
        "file access limits",
        "7-Zip can read and write every file your user can (.env, ~/.ssh, the output store), not just the archive",
        "it needs Linux 5.13 or newer with Landlock turned on (Ubuntu 22.04+ and RHEL 9 have it)",
    ),
}


def explain(missing: dict[str, str]) -> str:
    """Plain-words account of the layers that didn't apply: what's unprotected and how to fix it."""
    return " ".join(
        f"No {PLAIN[layer][0]} here ({why}): {PLAIN[layer][1]}. To fix: {PLAIN[layer][2]}."
        for layer, why in missing.items()
    )


def _libc() -> ctypes.CDLL:
    return ctypes.CDLL(None, use_errno=True)


def _landlock(read: list[str], execute: list[str], write: list[str]) -> None:
    libc = _libc()
    abi = libc.syscall(_SYS_LANDLOCK_CREATE_RULESET, None, 0, _LANDLOCK_CREATE_RULESET_VERSION)
    if abi < 1:
        raise OSError(ctypes.get_errno(), "landlock unavailable")
    handled = _ABI_ACCESS[min(abi, 3)]
    file_rights = _EXECUTE | _WRITE_FILE | _READ_FILE | (_TRUNCATE if abi >= 3 else 0)
    attr = struct.pack("Q", handled)
    ruleset = libc.syscall(_SYS_LANDLOCK_CREATE_RULESET, attr, len(attr), 0)
    if ruleset < 0:
        raise OSError(ctypes.get_errno(), "landlock_create_ruleset")
    rules = (
        [(p, _READ_FILE | _READ_DIR) for p in read]
        + [(p, _READ_FILE | _EXECUTE) for p in execute]
        + [(p, handled) for p in write]
    )
    for path, rights in rules:
        fd = os.open(path, os.O_PATH | os.O_CLOEXEC)
        try:
            allowed = rights & (file_rights if not os.path.isdir(path) else handled)
            beneath = struct.pack("=Qi", allowed, fd)
            if libc.syscall(_SYS_LANDLOCK_ADD_RULE, ruleset, _LANDLOCK_RULE_PATH_BENEATH, beneath, 0) != 0:
                raise OSError(ctypes.get_errno(), f"landlock_add_rule {path}")
        finally:
            os.close(fd)
    if libc.prctl(_PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "prctl(NO_NEW_PRIVS)")
    if libc.syscall(_SYS_LANDLOCK_RESTRICT_SELF, ruleset, 0) != 0:
        raise OSError(ctypes.get_errno(), "landlock_restrict_self")
    os.close(ruleset)


def _rlimits(max_file_bytes: int, max_memory_bytes: int) -> None:
    resource.setrlimit(resource.RLIMIT_FSIZE, (max_file_bytes, max_file_bytes))
    resource.setrlimit(resource.RLIMIT_AS, (max_memory_bytes, max_memory_bytes))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    if _libc().prctl(_PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "prctl(NO_NEW_PRIVS)")


def confine(
    *, read: list[str], execute: list[str], write: list[str], max_file_bytes: int, max_memory_bytes: int
) -> dict[str, str]:
    """Apply every layer that works here; returns each layer's outcome (`ok` or why not)."""
    outcome = {}
    for layer, apply in (
        ("rlimits", lambda: _rlimits(max_file_bytes, max_memory_bytes)),
        ("no_network", lambda: os.unshare(os.CLONE_NEWUSER | os.CLONE_NEWNET)),
        ("filesystem", lambda: _landlock(read, execute, write)),
    ):
        try:
            apply()
            outcome[layer] = "ok"
        except Exception as e:  # noqa: BLE001 -- best effort: a layer this machine refuses never stops the run
            outcome[layer] = f"{type(e).__name__}: {e}"
    return outcome


def main() -> None:
    """Parse the jail options, confine, report the outcome on `--report-fd`, then exec the command."""
    parser = argparse.ArgumentParser(prog="pyarchive.jail")
    parser.add_argument("--read", action="append", default=[])
    parser.add_argument("--exec", dest="execute", action="append", default=[])
    parser.add_argument("--write", action="append", default=[])
    parser.add_argument("--max-file-bytes", type=int, required=True)
    parser.add_argument("--max-memory-bytes", type=int, required=True)
    parser.add_argument("--report-fd", type=int, default=None)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    outcome = confine(
        read=args.read,
        execute=args.execute,
        write=args.write,
        max_file_bytes=args.max_file_bytes,
        max_memory_bytes=args.max_memory_bytes,
    )
    if args.report_fd is not None:
        os.write(args.report_fd, json.dumps(outcome).encode())
        os.close(args.report_fd)
    os.setsid()
    os.execve(command[0], command, {"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"})


def jail_command(
    command: list[str],
    *,
    read: list[str],
    execute: list[str],
    write: list[str],
    max_file_bytes: int,
    max_memory_bytes: int,
    report_fd: int | None = None,
) -> list[str]:
    """`command` wrapped in the launcher; with `report_fd` (a pipe end passed via `pass_fds`) it reports its layers."""
    options = [f"--read={p}" for p in read] + [f"--exec={p}" for p in execute] + [f"--write={p}" for p in write]
    if report_fd is not None:
        options.append(f"--report-fd={report_fd}")
    return [
        sys.executable,
        "-I",
        __file__,
        *options,
        f"--max-file-bytes={max_file_bytes}",
        f"--max-memory-bytes={max_memory_bytes}",
        "--",
        *command,
    ]


if __name__ == "__main__":
    main()
