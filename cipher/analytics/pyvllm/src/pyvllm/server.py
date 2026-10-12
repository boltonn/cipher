"""Start, stop and check the `vllm serve` process behind each model in `MODELS`.

Every model runs from this analytic's own `.venv-vllm` (vLLM pins its own torch), as
a background process group with its pid and log under `~/.local/state/pyvllm/`.
Auth is `VLLM_API_KEY` (environment or `.env`), handed to each `vllm serve` process.
"""

import asyncio
import os
import signal
import subprocess
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from loguru import logger

from pyvllm.models import MODELS, ModelSpec
from pyvllm.settings import settings

VLLM_BIN = Path(__file__).resolve().parents[2] / ".venv-vllm" / "bin" / "vllm"
STATE_DIR = Path.home() / ".local" / "state" / "pyvllm"
STARTUP_TIMEOUT_SECONDS = 900
# Triton/FlashInfer JIT paths this box's toolchain can't build; and strict tool calling off: its
# grammar only accepts arguments in schema order, silently cutting any the model writes out of order
# (Qwen writes `date_from` before `query`). The tool-call parser itself reads any order.
_VLLM_ENV = {
    "TRITON_ALLOW_NON_CONSTEXPR_GLOBALS": "1",
    "VLLM_USE_FLASHINFER_SAMPLER": "0",
    "VLLM_ENFORCE_STRICT_TOOL_CALLING": "0",
}


def pid_path(spec: ModelSpec) -> Path:
    """Where the pid of the process started for `spec` is kept."""
    return STATE_DIR / f"{spec.name}.pid"


def log_path(spec: ModelSpec) -> Path:
    """Where the server log of `spec` is written."""
    return STATE_DIR / f"{spec.name}.log"


def served_models(spec: ModelSpec) -> list[str] | None:
    """Model names served on `spec`'s port: None when nothing listens, ["?"] when it won't say (other key)."""
    try:
        response = httpx.get(f"{spec.base_url}/v1/models", headers=settings.auth_headers, timeout=3.0)
    except httpx.HTTPError:
        return None
    if not response.is_success:
        return ["?"]
    return [model["id"] for model in response.json().get("data", [])]


def is_healthy(spec: ModelSpec) -> bool:
    """True when `spec`'s own model is answering on its port."""
    return spec.served_name in (served_models(spec) or [])


def running_pid(spec: ModelSpec) -> int | None:
    """The pid of the process this analytic started for `spec`, if it is still alive."""
    try:
        pid = int(pid_path(spec).read_text())
        try:
            if os.waitpid(pid, os.WNOHANG)[0] == pid:  # our own child that already exited
                return None
        except ChildProcessError:
            pass  # started by another process (e.g. `pyvllm up`); kill(0) below decides
        os.kill(pid, 0)
        return pid
    except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError):
        return None


def start(spec: ModelSpec, gpu: int | None = None, wait: bool = True) -> None:
    """Launch `vllm serve` for `spec` in the background; with `wait`, block until it is healthy."""
    if is_healthy(spec):
        logger.info(f"{spec.name} already serving on {spec.base_url}")
        return
    if other := served_models(spec):
        raise RuntimeError(f"port {spec.port} is already serving {other} -- stop that before starting {spec.name}")
    if not VLLM_BIN.exists():
        raise RuntimeError(f"vLLM is not installed ({VLLM_BIN}) -- run `make install` in analytics/pyvllm")
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    command = [
        str(VLLM_BIN), "serve", spec.model,
        "--served-model-name", spec.served_name,
        "--port", str(spec.port),
        "--gpu-memory-utilization", str(spec.gpu_memory_utilization),
        *spec.args,
    ]  # fmt: skip
    environment = {**os.environ, **_VLLM_ENV, "CUDA_VISIBLE_DEVICES": str(spec.gpu if gpu is None else gpu)}
    if settings.api_key:
        environment["VLLM_API_KEY"] = settings.api_key
    with log_path(spec).open("w") as log:
        process = subprocess.Popen(
            command, env=environment, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            start_new_session=True,
        )  # fmt: skip
    pid_path(spec).write_text(str(process.pid))
    logger.info(
        f"Starting {spec.name} ({spec.served_name}) on GPU {environment['CUDA_VISIBLE_DEVICES']} -- log: {log_path(spec)}"
    )
    if wait:
        wait_healthy(spec, process)


def wait_healthy(spec: ModelSpec, process: subprocess.Popen | None = None) -> None:
    """Block until `spec` answers /health; raise if its process dies or the timeout passes."""
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if is_healthy(spec):
            logger.success(f"{spec.name} ready on {spec.base_url}")
            return
        if (process and process.poll() is not None) or (process is None and running_pid(spec) is None):
            raise RuntimeError(f"{spec.name} exited during startup -- see {log_path(spec)}")
        time.sleep(3)
    raise RuntimeError(f"{spec.name} not healthy after {STARTUP_TIMEOUT_SECONDS}s -- see {log_path(spec)}")


def stop(spec: ModelSpec, timeout: float = 60.0) -> bool:
    """Stop the process group this analytic started for `spec`. False when none was running."""
    pid = running_pid(spec)
    if pid is None:
        pid_path(spec).unlink(missing_ok=True)
        return False
    os.killpg(pid, signal.SIGTERM)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and running_pid(spec) is not None:
        time.sleep(1)
    if running_pid(spec) is not None:
        os.killpg(pid, signal.SIGKILL)
    pid_path(spec).unlink(missing_ok=True)
    logger.info(f"Stopped {spec.name}")
    return True


@asynccontextmanager
async def serving(name: str, gpu: int | None = None) -> AsyncIterator[ModelSpec]:
    """Make `name` available for the length of a job: reuse it if already up, else start it and stop it after."""
    spec = MODELS[name]
    if is_healthy(spec):
        yield spec
        return
    await asyncio.to_thread(start, spec, gpu)
    try:
        yield spec
    finally:
        await asyncio.to_thread(stop, spec)
