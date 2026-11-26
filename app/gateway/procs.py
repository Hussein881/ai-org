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
from collections.abc import Iterator
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
        self._owners: dict[int, str] = {}  # pid -> task that spawned it
        self._local = threading.local()

    @contextlib.contextmanager
    def owner(self, key: str) -> Iterator[None]:
        """Children spawned by this thread inside the block are tagged with `key`."""
        prev = getattr(self._local, "key", None)
        self._local.key = key
        try:
            yield
        finally:
            self._local.key = prev

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
            key = getattr(self._local, "key", None)
            if key is not None:
                self._owners[proc.pid] = key
            return proc

    def forget(self, proc: subprocess.Popen[str]) -> bool:
        """Drop a finished child. True if we signalled it."""
        with self._mu:
            self._procs.discard(proc)
            self._owners.pop(proc.pid, None)
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

    def kill_owned(self, keys: set[str], grace_s: float) -> int:
        """Terminate the children tagged with any of `keys` (a cancelled task's CLI)."""
        if not keys:
            return 0
        with self._mu:
            procs = [p for p in self._procs if self._owners.get(p.pid) in keys]
        if procs:
            self.terminate(procs, grace_s)
        return len(procs)

    def halt_now(self) -> None:
        """Permanent halt that never waits for the mutex (a hung Popen may hold it): the process
        is about to exit. Children already registered get SIGKILL; one still being spawned dies
        with the service cgroup."""
        self._closed = True
        self._halt.set()
        try:
            procs = list(self._procs)
        except RuntimeError:  # changed size while copying: take what we can
            procs = []
        for p in procs:
            self._killed.add(p.pid)
            _signal_group(p.pid, signal.SIGKILL)

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
