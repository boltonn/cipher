"""Which code a process runs: git branch + commit and the `uv.lock` it was synced from."""

import hashlib
import subprocess
from pathlib import Path


def workspace_root(start: Path | None = None) -> Path | None:
    """The nearest directory holding `uv.lock`, walking up from `start` (this file by default)."""
    for parent in (start or Path(__file__)).resolve().parents:
        if (parent / "uv.lock").exists():
            return parent
    return None


def _git(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=10, check=True)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def code_version(root: Path | None = None) -> dict[str, str | None]:
    """`{"branch", "sha", "lock_hash"}` of the workspace checkout; values are `None` when unknown."""
    root = root or workspace_root()
    if root is None:
        return {"branch": None, "sha": None, "lock_hash": None}
    lock = root / "uv.lock"
    return {
        "branch": _git(root, "rev-parse", "--abbrev-ref", "HEAD"),
        "sha": _git(root, "rev-parse", "HEAD"),
        "lock_hash": hashlib.sha256(lock.read_bytes()).hexdigest() if lock.exists() else None,
    }
