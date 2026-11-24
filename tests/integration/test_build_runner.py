"""S00 acceptance for scripts/build-runner.sh (spec: docs/TASKS.md 'Build runner')."""

import json
import os
import subprocess
from pathlib import Path

RUNNER = Path(__file__).resolve().parents[2] / "scripts" / "build-runner.sh"


class Env:
    def __init__(self, tmp: Path, tasks: str, fake_body: str = "") -> None:
        self.tmp = tmp
        self.tasks = tmp / "T.md"
        self.tasks.write_text(tasks)
        self.records = tmp / "slices"
        self.records.mkdir()
        self.marker = tmp / "launched"
        self.fake = tmp / "fakeclaude"
        self.fake.write_text(
            "#!/bin/bash\n"
            f'echo "$@" >> {tmp}/argv\n'
            f"env > {tmp}/childenv\n"
            f"touch {self.marker}\n" + fake_body
        )
        self.fake.chmod(0o755)

    def run(self, **extra: str) -> subprocess.CompletedProcess[str]:
        env = {k: v for k, v in os.environ.items() if not k.endswith(("_API_KEY", "_TOKEN"))}
        env.update(
            TASKS_FILE=str(self.tasks),
            RUNNER_LOG=str(self.tmp / "r.log"),
            RECORD_DIR=str(self.records),
            CLAUDE_CMD=str(self.fake),
            NOTIFY_LOG_ONLY="1",
            PROBE_SECS="1",
            **extra,
        )
        return subprocess.run(  # noqa: S603
            ["bash", str(RUNNER)],  # noqa: S607
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )


def done_body(env_dir: Path, sid: str, mark: bool = True) -> str:
    sed = f"sed -i -E 's/^(### {sid}: .*)`\\[.\\]`/\\1`[x]`/' {env_dir}/T.md\n" if mark else ""
    return (
        sed
        + f"echo done > {env_dir}/slices/{sid}.md\n"
        + "echo '"
        + json.dumps({"result": "blah\nSLICE_DONE " + sid})
        + "'\n"
    )


SLICE = "# t\n### S99: Dummy\nTier T1 · Model `haiku` · Depends: bootstrap\n- [ ] x\n"


def tasks(marker: str = " ") -> str:
    return SLICE.replace("### S99: Dummy", f"### S99: Dummy `[{marker}]`")


def test_dry_run_moves_and_restores(tmp_path: Path) -> None:
    e = Env(tmp_path, tasks())
    r = e.run(DRY_RUN="1")
    assert r.returncode == 0 and "DRY_RUN ok S99" in r.stdout
    assert "Dummy `[ ]`" in e.tasks.read_text() and not (e.records / "S99.md").exists()
    assert "[ ]→[~]→[x]" in (tmp_path / "r.log").read_text()


def test_launch_args_and_scrubbed_env(tmp_path: Path) -> None:
    e = Env(tmp_path, tasks())
    e.fake.write_text(e.fake.read_text() + done_body(tmp_path, "S99"))
    r = e.run(NOTION_TOKEN="n-secret", NOTION_INBOX_DB_ID="db", NTFY_TOKEN="t")  # noqa: S106
    assert r.returncode == 0 and "Dummy `[x]`" in e.tasks.read_text()
    argv = (tmp_path / "argv").read_text()
    assert "--model haiku" in argv and "--effort low" in argv and "--output-format json" in argv
    child = (tmp_path / "childenv").read_text()
    assert "NOTION" not in child and "NTFY" not in child and "n-secret" not in child


def test_planted_key_blocks_and_never_launches(tmp_path: Path) -> None:
    e = Env(tmp_path, tasks())
    r = e.run(ANTHROPIC_API_KEY="planted-fake")
    assert r.returncode == 1 and not e.marker.exists()
    assert "Dummy `[!]`" in e.tasks.read_text()
    assert "planted-fake" not in r.stdout + r.stderr


def test_done_without_marker_or_record_is_blocked(tmp_path: Path) -> None:
    e = Env(tmp_path, tasks())
    e.fake.write_text(e.fake.read_text() + done_body(tmp_path, "S99", mark=False))
    e.run()
    assert "Dummy `[!]`" in e.tasks.read_text()


def test_stops_behind_slice_needing_founder(tmp_path: Path) -> None:
    e = Env(
        tmp_path,
        "### S00: A `[?]`\nDepends: x\n### S01: B `[ ]`\nTier T1 · Model `sonnet` · Depends S00\n",
    )
    assert e.run().returncode == 0
    assert "S01: B `[ ]`" in e.tasks.read_text() and not e.marker.exists()


def test_in_progress_slice_resumes_first(tmp_path: Path) -> None:
    e = Env(tmp_path, "### S01: A `[ ]`\nModel `sonnet`\n### S02: B `[~]`\nModel `sonnet`\n")
    e.fake.write_text(e.fake.read_text() + 'echo \'{"result":"BLOCKED S02 nope"}\'\n')
    e.run()
    assert "S02: B `[!]`" in e.tasks.read_text()


def test_error_retries_once_then_blocks(tmp_path: Path) -> None:
    e = Env(tmp_path, tasks())
    e.fake.write_text(e.fake.read_text() + "echo 'garbage'\nexit 1\n")
    e.run()
    assert (tmp_path / "argv").read_text().count("\n") == 2
    assert "Dummy `[!]`" in e.tasks.read_text()


def test_usage_limit_is_not_a_failure(tmp_path: Path) -> None:
    e = Env(tmp_path, tasks())
    body = (
        f"n=$(cat {tmp_path}/n 2>/dev/null || echo 0); echo $((n+1)) > {tmp_path}/n\n"
        'if [ "$n" = 0 ]; then echo \'{"result":"Claude usage limit reached"}\'; exit 1; fi\n'
        'if [ "$1" = "-p" ] && [ "$2" = "ok" ]; then echo ok; exit 0; fi\n'
    )
    e.fake.write_text(e.fake.read_text() + body + done_body(tmp_path, "S99"))
    e.run()
    assert "Dummy `[x]`" in e.tasks.read_text()
    assert "retrying once" not in (tmp_path / "r.log").read_text()


def test_env_check_must_print_env_clean(tmp_path: Path) -> None:
    e = Env(tmp_path, tasks())
    chk = tmp_path / "chk.sh"
    chk.write_text("#!/bin/bash\nexit 0\n")
    r = e.run(ENV_CHECK=str(chk))
    assert r.returncode == 1 and not e.marker.exists()
    assert "Dummy `[!]`" in e.tasks.read_text()


def test_phase_milestone_notified_once_phase_complete(tmp_path: Path) -> None:
    md = "## Phase A: See it\n### S98: One `[x]`\nModel `haiku`\n"
    md += "### S99: Two `[ ]`\nModel `haiku` · Depends S98\n"
    e = Env(tmp_path, md)
    e.fake.write_text(e.fake.read_text() + done_body(tmp_path, "S99"))
    e.run()
    assert "Milestone: Phase A: See it complete" in (tmp_path / "r.log").read_text()
