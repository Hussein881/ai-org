"""Registry of running CLI subprocesses so a stop or shutdown can kill them.

Each child leads its own process group. One lock covers "check halted + spawn" and "set halted +
snapshot", so nothing can start after a halt without being seen by it.
"""

import contextlib
import os
import signal
import subprocess
import threading
import time
from typing import Any

from app.gateway.types import ProviderError


def _signal_group(pgid: int, sig: int) -> bool:
    try:
        os.killpg(pgid, sig)
    except (ProcessLookupError, PermissionError):
        return False
    return True


class ProcRegistry:
    def __init__(self) -> None:
        self._mu = threading.Lock()
        self._procs: set[subprocess.Popen[str]] = set()
        self._killed: set[int] = set()
        self._halt = threading.Event()
        self._closed = False

    def halted(self) -> bool:
        return self._halt.is_set()

    def wait(self, seconds: float) -> bool:
        """Sleep that a halt interrupts. True if halted."""
        return self._halt.wait(seconds)

    def spawn(self, argv: list[str], **kw: Any) -> subprocess.Popen[str]:
        with self._mu:
            if self._halt.is_set():
                raise ProviderError("halted")
            proc: subprocess.Popen[str] = subprocess.Popen(  # noqa: S603
                argv, start_new_session=True, **kw
            )
            self._procs.add(proc)
            return proc

    def forget(self, proc: subprocess.Popen[str]) -> bool:
        """Drop a finished child. True if we signalled it."""
        with self._mu:
            self._procs.discard(proc)
            killed = proc.pid in self._killed
            self._killed.discard(proc.pid)
            return killed

    def terminate(self, procs: list[subprocess.Popen[str]], grace_s: float) -> threading.Thread:
        """SIGTERM each group now; a background thread SIGKILLs whatever survives the grace."""
        with self._mu:
            self._killed.update(p.pid for p in procs)
        groups = [p.pid for p in procs]
        for pgid in groups:
            _signal_group(pgid, signal.SIGTERM)

        def reap() -> None:
            deadline = time.monotonic() + grace_s
            alive = list(zip(groups, procs, strict=True))
            while alive and time.monotonic() < deadline:
                time.sleep(0.05)
                for _, p in alive:
                    p.poll()
                alive = [(g, p) for g, p in alive if _signal_group(g, 0)]
            for pgid, p in alive:
                _signal_group(pgid, signal.SIGKILL)
                with contextlib.suppress(subprocess.TimeoutExpired):
                    p.wait(timeout=5)

        thread = threading.Thread(target=reap, name="aiorg-reaper")  # non-daemon: must finish
        thread.start()
        return thread

    def halt(self, grace_s: float) -> threading.Thread | None:
        with self._mu:
            self._halt.set()
            snapshot = list(self._procs)
        return self.terminate(snapshot, grace_s) if snapshot else None

    def close(self, grace_s: float) -> threading.Thread | None:
        """Permanent halt (process shutdown)."""
        self._closed = True
        return self.halt(grace_s)

    def reopen(self) -> None:
        with self._mu:
            if not self._closed:
                self._halt.clear()

    def reset(self) -> None:
        """Tests only."""
        with self._mu:
            self._closed = False
            self._halt.clear()


REGISTRY = ProcRegistry()
