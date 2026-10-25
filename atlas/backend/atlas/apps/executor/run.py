"""Executor entrypoint: the Celery ``execution`` worker plus the live market-data stream.

Both need the broker credentials, which only the executor container receives, so they run
side by side here instead of in separate containers. If either one exits, the other is
stopped and the process exits non-zero, so the container restart policy brings both back.
SIGTERM/SIGINT stop both cleanly.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
import subprocess
import sys

from atlas.apps.executor.stream_service import LiveDataService, build_service
from atlas.core.configuration.settings import get_settings
from atlas.core.observability.logging import configure_logging, get_logger

log = get_logger(__name__)

CELERY_CMD = [
    sys.executable,
    "-m",
    "celery",
    "-A",
    "atlas.apps.worker.celery_app",
    "worker",
    "-Q",
    "execution",
    "-n",
    "executor@%h",
    "--concurrency",
    "1",
]


async def supervise(worker: subprocess.Popen[bytes], service: LiveDataService | None) -> int:
    loop = asyncio.get_running_loop()
    stopping = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stopping.set)
    stream_task = asyncio.create_task(service.run()) if service else None
    exit_code = 0
    try:
        while not stopping.is_set():
            code = worker.poll()
            if code is not None:
                log.error("executor_worker_exited", code=code)
                exit_code = code or 1
                break
            if stream_task is not None and stream_task.done():
                exc = stream_task.exception()
                log.error("executor_stream_exited", error=type(exc).__name__ if exc else None)
                exit_code = 1
                break
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stopping.wait(), timeout=1.0)
    finally:
        if service is not None:
            service.stop()
        if stream_task is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(stream_task, timeout=15)
        if worker.poll() is None:
            worker.send_signal(signal.SIGTERM)  # Celery warm shutdown
            try:
                await asyncio.to_thread(worker.wait, 60)
            except subprocess.TimeoutExpired:
                worker.kill()
    return exit_code


def main() -> int:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json, service="executor")
    service = build_service(settings) if settings.stream_enabled else None
    worker = subprocess.Popen(CELERY_CMD)  # noqa: S603 - fixed argv, no shell
    return asyncio.run(supervise(worker, service))


if __name__ == "__main__":
    raise SystemExit(main())
