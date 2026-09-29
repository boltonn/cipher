"""Per-stage environments: a `cipher` command installs only the analytics it runs.

The base `cipher` install is just orchestration + datastores. A command that needs a
heavy analytic calls `ensure_stage_env("<extra>")` first; unless that extra is
already active, the process re-launches itself as

    uv run --frozen --project <workspace> --package cipher-orchestration --extra <extra> cipher <same args>

`uv run` syncs inexactly, so the first call installs the stage from `uv.lock` and
later calls only verify it -- nothing another stage installed is removed. Set
`CIPHER_STAGE_ENV_ISOLATED=1` for a throwaway env per call (`uv run --isolated`,
closest to a one-container-per-step orchestrator), or `CIPHER_AUTO_ENV=0` to run in
whatever environment is active (e.g. a hand-built one).
"""

import os
import shutil
import sys
from pathlib import Path

from loguru import logger

_ACTIVE_VAR = "CIPHER_STAGE_ENV"


def _workspace_root() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        if (parent / "uv.lock").exists():
            return parent
    return None


def ensure_stage_env(*extras: str) -> None:
    """Re-exec this command under `uv run --extra ...` unless `extras` are already active."""
    active = {e for e in os.environ.get(_ACTIVE_VAR, "").split(",") if e}
    missing = [e for e in extras if e not in active]
    if not missing or os.environ.get("CIPHER_AUTO_ENV", "1") == "0":
        return
    uv = shutil.which("uv")
    root = _workspace_root()
    if uv is None or root is None:
        logger.warning(f"uv/workspace not found -- running without syncing extras {missing}")
        return

    wanted = sorted(active | set(extras))
    command = [uv, "run", "--frozen", "--project", str(root), "--package", "cipher-orchestration"]
    if os.environ.get("CIPHER_STAGE_ENV_ISOLATED") == "1":
        command.append("--isolated")
    for extra in wanted:
        command += ["--extra", extra]
    command += ["cipher", *sys.argv[1:]]
    logger.info(f"Syncing stage env {wanted} and re-running under uv")
    os.execve(uv, command, {**os.environ, _ACTIVE_VAR: ",".join(wanted)})
