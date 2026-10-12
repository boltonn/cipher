"""`cipher worker`: claim approved plan steps from Postgres and run each as a `cipher` subprocess.

One worker per host and pool (docs/pipeline-runner.md). A `cpu` worker runs up to `slots`
steps at once; a `gpu` worker one step per GPU it is given, with `CUDA_VISIBLE_DEVICES`
(and `CIPHER_GPU`, for steps that start a model server) set to that GPU.

The step's command finds its row in `CIPHER_RUN_ID` and records into it (`record_run`);
the worker heartbeats the row every pass (~2 s), notices `cancelling` and interrupts the command, and
closes the row from the exit code if the command didn't.

SIGTERM / Ctrl-C drains: no new claims, running steps finish. A second one interrupts them.
"""

import asyncio
import contextlib
import os
import signal
import socket
import sys
from collections import deque
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from cipher.datastores.postgres.repositories import PostgresEnrichmentRunRepository
from cipher.orchestration.run_recorder import GPU_ENV, RUN_ID_ENV
from cipher.orchestration.session import get_async_engine_from_settings
from cipher.schemas.ingestion.run_plan import RunStatus, StepPool, step_command
from cipher.utils.version import code_version

CANCEL_GRACE_SECONDS = 120
"""After asking a step to stop (SIGINT), how long before it is terminated, then killed."""


@dataclass
class _Step:
    run_id: str
    label: str
    process: asyncio.subprocess.Process
    log_path: Path
    gpu: str | None
    date_interrupted: float | None = None
    signals_sent: list[int] = field(default_factory=list)


def _log_tail(path: Path, lines: int = 40) -> str:
    try:
        with path.open(errors="replace") as handle:
            return "".join(deque(handle, maxlen=lines))[-4000:]
    except OSError:
        return ""


class Worker:
    """Claims and runs plan steps for one pool on this host."""

    def __init__(
        self,
        *,
        pool: StepPool,
        slots: int,
        gpus: list[str],
        caps: dict[str, int],
        max_hosts_per_step: int,
        is_strict_version: bool,
        poll_seconds: float,
        log_dir: Path,
    ) -> None:
        self.pool = pool
        self.gpus = gpus
        self.slots = len(gpus) if pool is StepPool.GPU else slots
        self.caps = caps
        self.max_hosts_per_step = max_hosts_per_step
        self.is_strict_version = is_strict_version
        self.poll_seconds = poll_seconds
        self.log_dir = log_dir
        self.name = f"{socket.gethostname()}:{os.getpid()}"
        self.engine = get_async_engine_from_settings()
        self.running: dict[str, _Step] = {}
        self.stop_requests = 0

    def _free_gpu(self) -> str | None:
        busy = {step.gpu for step in self.running.values()}
        return next((gpu for gpu in self.gpus if gpu not in busy), None)

    async def _claim(self):
        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            return await PostgresEnrichmentRunRepository(session=session).claim_next(
                pool=self.pool.value,
                worker=self.name,
                caps=self.caps,
                ran_on=code_version(),
                is_strict_version=self.is_strict_version,
                max_hosts_per_step=self.max_hosts_per_step,
            )

    async def _start(self, row) -> None:
        gpu = self._free_gpu() if self.pool is StepPool.GPU else None
        argv = step_command(row.enrichment_type, row.params, dataset_id=row.dataset_id)
        environment = {**os.environ, RUN_ID_ENV: row.id}
        if gpu is not None:
            environment |= {"CUDA_VISIBLE_DEVICES": gpu, GPU_ENV: gpu}
        log_path = self.log_dir / f"{row.id}.log"
        approved = ((row.code_version or {}).get("approved") or {}).get("sha")
        ran = ((row.code_version or {}).get("ran") or {}).get("sha")
        if approved and ran and approved != ran:
            logger.warning(f"{row.enrichment_type}: approved on {approved[:8]}, running on {ran[:8]}")
        with log_path.open("ab") as log:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                "from cipher.orchestration.cli import app; app()",
                *argv,
                stdout=log,
                stderr=asyncio.subprocess.STDOUT,
                env=environment,
                start_new_session=True,
            )
        async with AsyncSession(self.engine) as session:
            await PostgresEnrichmentRunRepository(session=session).set_process(
                row.id,
                {
                    "host": socket.gethostname(),
                    "worker_pid": os.getpid(),
                    "pid": process.pid,
                    "log": str(log_path),
                    "gpu": gpu,
                },
            )
        label = f"{row.enrichment_type} on {row.dataset_id}" + (f" (GPU {gpu})" if gpu is not None else "")
        self.running[row.id] = _Step(run_id=row.id, label=label, process=process, log_path=log_path, gpu=gpu)
        logger.info(f"Started {label}: cipher {' '.join(argv)} -- log {log_path}")

    def _signal(self, step: _Step, signum: int) -> None:
        if signum in step.signals_sent:
            return
        step.signals_sent.append(signum)
        with contextlib.suppress(ProcessLookupError):
            os.killpg(step.process.pid, signum)

    def _interrupt(self, step: _Step) -> None:
        """SIGINT now, SIGTERM after the grace period, SIGKILL after twice that."""
        if step.date_interrupted is None:
            step.date_interrupted = monotonic()
            logger.info(f"Stopping {step.label}")
        waited = monotonic() - step.date_interrupted
        self._signal(step, signal.SIGINT)
        if waited > CANCEL_GRACE_SECONDS:
            self._signal(step, signal.SIGTERM)
        if waited > 2 * CANCEL_GRACE_SECONDS:
            self._signal(step, signal.SIGKILL)

    async def _reap(self) -> None:
        for run_id, step in list(self.running.items()):
            if step.process.returncode is None:
                continue
            del self.running[run_id]
            exit_code = step.process.returncode
            with suppress(ProcessLookupError):  # nothing of the step may outlive it (e.g. `uv run` killed, child left)
                os.killpg(step.process.pid, signal.SIGKILL)
            async with AsyncSession(self.engine, expire_on_commit=False) as session:
                await PostgresEnrichmentRunRepository(session=session).finish_step(
                    run_id, exit_code=exit_code, error_message=_log_tail(step.log_path) or f"exit code {exit_code}"
                )
            logger.info(f"Finished {step.label}: exit code {exit_code}")

    async def _heartbeat(self) -> None:
        async with AsyncSession(self.engine) as session:
            statuses = await PostgresEnrichmentRunRepository(session=session).heartbeat(list(self.running))
        for run_id, step in self.running.items():
            if statuses.get(run_id) == RunStatus.CANCELLING.value or self.stop_requests > 1:
                self._interrupt(step)

    def _request_stop(self) -> None:
        self.stop_requests += 1
        if self.stop_requests == 1:
            logger.info("Draining: no new steps; running ones finish (signal again to interrupt them)")
        else:
            logger.info("Interrupting running steps")
            for step in self.running.values():
                self._interrupt(step)

    async def run(self) -> None:
        """Claim, run, heartbeat and reap until asked to stop and nothing is left running."""
        self.log_dir.mkdir(parents=True, exist_ok=True)
        loop = asyncio.get_running_loop()
        for signum in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(signum, self._request_stop)
        logger.info(
            f"Worker {self.name}: pool {self.pool.value}, {self.slots} slot(s)"
            + (f" on GPU {', '.join(self.gpus)}" if self.gpus else "")
            + f", service caps {self.caps or 'llm=1'}"
        )
        while self.stop_requests == 0 or self.running:
            await self._reap()
            while self.stop_requests == 0 and len(self.running) < self.slots:
                row = await self._claim()
                if row is None:
                    break
                await self._start(row)
            if self.running:  # also how a cancel is noticed, so every pass
                await self._heartbeat()
            await asyncio.sleep(self.poll_seconds if not self.running else min(self.poll_seconds, 2))
        await self.engine.dispose()
        logger.info("Worker stopped")
