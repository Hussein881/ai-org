"""Run vendor CLIs in a scrubbed environment (the worker holds API keys; the CLIs must not)."""

import os
import re
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path

from app.gateway.procs import REGISTRY
from app.gateway.redact import SECRET_NAME_RE
from app.gateway.types import ProviderError

ENV_ALLOW = ("HOME", "PATH", "USER", "LOGNAME", "LANG", "TERM", "XDG_RUNTIME_DIR")
_DEFAULTS = {"USER": "aiorg", "LOGNAME": "aiorg", "LANG": "C.UTF-8", "TERM": "dumb"}
_SAFE_VALUE = re.compile(r"^[\w./:@+\-]{0,512}$")
_MAX_OUTPUT = 5_000_000
TIMEOUT_KILL_GRACE_S = 5.0


def scrubbed_env() -> dict[str, str]:
    """Allowlist copy of the environment. Names AND values are validated."""
    env: dict[str, str] = {}
    for name in ENV_ALLOW:
        value = os.environ.get(name, _DEFAULTS.get(name))
        if value is None:
            continue
        if name == "PATH":
            ok = all(_SAFE_VALUE.match(p) for p in value.split(":"))
        else:
            ok = bool(_SAFE_VALUE.match(value))
        if not ok:
            raise ProviderError("env_value_rejected")
        env[name] = value
    if any(SECRET_NAME_RE.match(k) for k in env):
        raise ProviderError("env_secret_name")
    return env


def run_cli(argv: Sequence[str], stdin: str, timeout_s: float) -> tuple[int, str, str]:
    """No shell; prompt on stdin (never argv); empty temp cwd; killed on timeout."""
    env = scrubbed_env()
    with tempfile.TemporaryDirectory(prefix="aiorg-cli-") as cwd:
        try:
            proc = REGISTRY.spawn(
                list(argv),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                cwd=cwd,
                shell=False,
            )
        except FileNotFoundError:
            raise ProviderError("binary_missing") from None
        try:
            out, err = proc.communicate(stdin, timeout=timeout_s)
        except subprocess.TimeoutExpired:
            REGISTRY.terminate([proc], TIMEOUT_KILL_GRACE_S).join()
            proc.communicate()
            REGISTRY.forget(proc)
            raise ProviderError("timeout") from None
        except BaseException:
            REGISTRY.terminate([proc], 0).join()
            REGISTRY.forget(proc)
            raise
        if REGISTRY.forget(proc):
            raise ProviderError("killed")
    return proc.returncode, out[:_MAX_OUTPUT], err[:_MAX_OUTPUT]


def env_is_clean() -> bool:
    """Run scripts/check-env-clean.sh under the scrubbed environment (launch-path guard)."""
    script = Path(__file__).resolve().parents[2] / "scripts" / "check-env-clean.sh"
    if not script.exists():
        return False  # fail closed: live CLI calls need the guard script
    code, out, _ = run_cli(["bash", str(script)], "", 10)
    return code == 0 and out.strip() == "ENV_CLEAN"
