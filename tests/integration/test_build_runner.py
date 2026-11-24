"""S00 acceptance: runner dry-run flips a dummy slice; a key in env blocks the launch."""

import os
import subprocess
from pathlib import Path

RUNNER = Path(__file__).resolve().parents[2] / "scripts" / "build-runner.sh"


def _run(
    tmp_path: Path, extra_env: dict[str, str], claude: str | None = None
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    tasks = tmp_path / "T.md"
    tasks.write_text("# t\n### S99: Dummy `[ ]`\nbody\n")
    marker = tmp_path / "launched"
    fake = tmp_path / "fakeclaude"
    fake.write_text(f"#!/bin/bash\ntouch {marker}\necho 'SLICE_DONE S99'\n")
    fake.chmod(0o755)
    env = {k: v for k, v in os.environ.items() if not k.endswith(("_API_KEY", "_TOKEN"))}
    env.update(
        TASKS_FILE=str(tasks),
        RUNNER_LOG=str(tmp_path / "r.log"),
        CLAUDE_CMD=claude or str(fake),
        **extra_env,
    )
    r = subprocess.run(["bash", str(RUNNER)], env=env, capture_output=True, text=True, check=False)  # noqa: S603, S607
    return r, tasks, marker


def test_dry_run_marks_done(tmp_path: Path) -> None:
    r, tasks, _ = _run(tmp_path, {"DRY_RUN": "1"})
    assert r.returncode == 0
    assert "S99: Dummy `[x]`" in tasks.read_text()


def test_clean_env_launches_claude(tmp_path: Path) -> None:
    r, tasks, marker = _run(tmp_path, {})
    assert r.returncode == 0 and marker.exists()
    assert "`[x]`" in tasks.read_text()


def test_planted_key_blocks_and_never_launches(tmp_path: Path) -> None:
    r, tasks, marker = _run(tmp_path, {"ANTHROPIC_API_KEY": "planted-fake"})
    assert r.returncode == 1
    assert not marker.exists()
    assert "`[!]`" in tasks.read_text()
    assert "planted-fake" not in r.stdout + r.stderr
