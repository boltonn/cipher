"""Start the local pyocr engine for the length of a job, so OCR runs like any other stage.

vLLM pins its own torch, so the engine lives in `analytics/pyocr/.venv-vllm` and is a
separate process on this machine. `local_service` reuses one that is already listening
and otherwise launches it, waits for the model to load, and stops it afterwards.
"""

import asyncio
import os
import subprocess
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

import httpx
from loguru import logger

from pyocr.client import DEFAULT_BASE_URL

VLLM_API = Path(__file__).resolve().parents[2] / ".venv-vllm" / "bin" / "pyocr-api"
STARTUP_TIMEOUT_SECONDS = 600


async def _is_healthy(base_url: str) -> bool:
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=5.0) as client:
            return (await client.get("/health")).is_success
    except httpx.HTTPError:
        return False


@asynccontextmanager
async def local_service(base_url: str = DEFAULT_BASE_URL, log_path: Path | None = None) -> AsyncIterator[str]:
    """Yield a healthy pyocr URL: the one already running at `base_url`, or one started for this block.

    The engine picks its GPU from `CUDA_VISIBLE_DEVICES` and its settings from `OCR__*`.
    """
    if await _is_healthy(base_url):
        yield base_url
        return
    if not VLLM_API.exists():
        raise RuntimeError(f"pyocr engine is not installed ({VLLM_API}) -- run `make install-vllm` in analytics/pyocr")

    log_path = log_path or VLLM_API.parents[2] / "pyocr-local.log"
    environment = {**os.environ, "PORT": str(urlparse(base_url).port or 8010), "OCR__BACKEND": "vllm"}
    logger.info(f"Starting the local pyocr engine (log: {log_path})")
    with log_path.open("w") as log:
        process = subprocess.Popen([str(VLLM_API)], env=environment, stdout=log, stderr=subprocess.STDOUT)  # noqa: ASYNC220
    try:
        for _ in range(STARTUP_TIMEOUT_SECONDS // 2):
            if process.poll() is not None:
                raise RuntimeError(f"pyocr engine exited during startup -- see {log_path}")
            if await _is_healthy(base_url):
                break
            await asyncio.sleep(2)
        else:
            raise RuntimeError(f"pyocr engine did not become healthy in {STARTUP_TIMEOUT_SECONDS}s -- see {log_path}")
        yield base_url
    finally:
        process.terminate()
        try:
            await asyncio.to_thread(process.wait, 60)
        except subprocess.TimeoutExpired:
            process.kill()
