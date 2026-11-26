"""Test-only fault injection: SIGKILL ourselves at a named point. Inert unless gateway_mode=fake."""

import os
import signal

from app.config import get_settings


def point(name: str) -> None:
    s = get_settings()
    if s.gateway_mode == "fake" and s.test_crash_point == name:
        os.kill(os.getpid(), signal.SIGKILL)
