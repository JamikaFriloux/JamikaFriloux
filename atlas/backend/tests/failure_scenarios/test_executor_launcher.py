import asyncio
import subprocess
import sys

from atlas.apps.executor import run as launcher


class FakeService:
    def __init__(self, fail_after: float | None = None):
        self.fail_after = fail_after
        self.stopped = False
        self._stop = None

    async def run(self):
        self._stop = asyncio.Event()
        if self.fail_after is not None:
            await asyncio.sleep(self.fail_after)
            raise RuntimeError("stream crashed")
        await self._stop.wait()

    def stop(self):
        self.stopped = True
        if self._stop:
            self._stop.set()


def _worker(code: str) -> subprocess.Popen[bytes]:
    return subprocess.Popen([sys.executable, "-c", code])  # noqa: S603


def test_worker_exit_stops_stream_and_propagates_code():
    service = FakeService()
    worker = _worker("import sys, time; time.sleep(0.3); sys.exit(3)")
    assert asyncio.run(launcher.supervise(worker, service)) == 3
    assert service.stopped


def test_stream_crash_terminates_worker():
    worker = _worker("import time; time.sleep(60)")
    code = asyncio.run(launcher.supervise(worker, FakeService(fail_after=0.2)))
    assert code == 1
    assert worker.poll() is not None  # terminated, not left running


def test_worker_only_when_stream_disabled():
    worker = _worker("import sys; sys.exit(0)")
    assert asyncio.run(launcher.supervise(worker, None)) == 1  # clean exit still restarts
