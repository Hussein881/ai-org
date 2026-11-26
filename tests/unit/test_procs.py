"""The process registry: a halt must kill every CLI child and let nothing new start."""

import threading
import time

import pytest

from app.gateway.procs import REGISTRY
from app.gateway.subproc import run_cli
from app.gateway.types import ProviderError
from app.workers.supervisor import available_mb


@pytest.fixture(autouse=True)
def clean_registry():
    REGISTRY.reset()
    yield
    REGISTRY.reset()


def _halt_soon(grace, delay=0.5):
    timer = threading.Timer(delay, lambda: REGISTRY.halt(grace))
    timer.start()
    return timer


def _run_expecting_kill(argv):
    started = time.monotonic()
    with pytest.raises(ProviderError) as e:
        run_cli(argv, "", 60)
    return e.value.kind, time.monotonic() - started


def test_halt_kills_the_child_and_its_grandchild():
    _halt_soon(grace=10)
    # the grandchild holds the output pipes: only killing the whole group lets communicate() return
    kind, took = _run_expecting_kill(["bash", "-c", "sleep 60 & wait"])
    assert kind == "killed" and took < 3


def test_child_ignoring_sigterm_is_killed_after_the_grace_period():
    _halt_soon(grace=1.5)
    kind, took = _run_expecting_kill(["bash", "-c", "trap '' TERM; sleep 60"])
    assert kind == "killed" and 1.8 <= took < 5


def test_nothing_starts_while_halted_and_close_is_permanent():
    REGISTRY.halt(1)
    with pytest.raises(ProviderError) as e:
        run_cli(["true"], "", 5)
    assert e.value.kind == "halted"
    REGISTRY.reopen()
    assert run_cli(["true"], "", 5)[0] == 0
    REGISTRY.close(1)
    REGISTRY.reopen()
    assert REGISTRY.halted()


def test_meminfo_parsing_fails_closed():
    assert available_mb("MemTotal: 100 kB\nMemAvailable:    2097152 kB\n") == 2048
    assert available_mb("garbage") == 0
