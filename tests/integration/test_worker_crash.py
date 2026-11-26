"""S04 acceptance with real worker processes: kill -9, emergency stop, concurrency, exit codes."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core import control, effects, tasks
from app.db.models import Task
from app.db.session import engine
from app.org.seed import seed_roles


def children(pid):
    out = []
    for stat in Path("/proc").glob("[0-9]*/stat"):
        try:
            fields = stat.read_text().rsplit(")", 1)[1].split()
        except OSError:
            continue
        if int(fields[1]) == pid and fields[0] != "Z":
            out.append(int(stat.parent.name))
    return out


def ignores_sigterm(pid):
    for line in Path(f"/proc/{pid}/status").read_text().splitlines():
        if line.startswith("SigIgn:"):
            return bool(int(line.split()[1], 16) & (1 << (signal.SIGTERM - 1)))
    return False


class Worker:
    def __init__(self, url, log: Path, **overrides):
        env = {
            **os.environ,
            "AIORG_DATABASE_URL": url,
            "AIORG_GATEWAY_MODE": "fake",
            "AIORG_CEO_LIVE_REPLY": "true",
            "AIORG_ECHO_SECONDS": "0.2",
            "AIORG_MIN_FREE_RAM_MB": "1",
            "AIORG_STOP_GRACE_S": "2",
            **{f"AIORG_{k.upper()}": str(v) for k, v in overrides.items()},
        }
        self.log = log
        with log.open("ab") as out:
            self.proc = subprocess.Popen(
                [sys.executable, "-m", "app.workers.host"], env=env, stdout=out, stderr=out
            )

    def exit_code(self, timeout=30):
        return self.proc.wait(timeout=timeout)

    def stop(self):
        if self.proc.poll() is None:
            kids = children(self.proc.pid)
            self.proc.kill()
            self.proc.wait(timeout=10)
            for pid in kids:  # outside systemd there is no cgroup to clean these up
                try:
                    os.killpg(pid, signal.SIGKILL)
                except OSError:
                    pass


@pytest.fixture
def start(db_url, tmp_path):
    with Session(engine()) as s:
        seed_roles(s, "roles")
    workers = []

    def _start(**kw):
        w = Worker(db_url, tmp_path / f"worker{len(workers)}.log", **kw)
        workers.append(w)
        return w

    yield _start
    for w in workers:
        w.stop()


def add(title="t"):
    with Session(engine()) as s:
        return tasks.create_task(s, title=title, description="", assignee="ceo", actor="f").id


def rows(query):
    with Session(engine()) as s:
        return [tuple(r) for r in s.execute(text(query)).all()]


def state(task_id):
    with Session(engine()) as s:
        t = s.get(Task, task_id)
        return t.status, t.status_reason


def wait_for(predicate, timeout=30.0, what="condition"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for {what}")


def completions(task_id):
    with Session(engine()) as s:
        return s.execute(
            text(
                "select count(*) from events where kind = 'task.status' "
                "and task_id = :i and payload->>'to' = 'completed'"
            ),
            {"i": task_id},
        ).scalar_one()


@pytest.mark.parametrize("point", ["before_intent", "after_effect_done", "after_complete"])
def test_kill9_resumes_once_with_one_model_call(start, point):
    tid = add()
    assert start(test_crash_point=point).exit_code() == -signal.SIGKILL
    start()
    wait_for(lambda: state(tid)[0] == "completed", what="completion")
    open_jobs = (
        "select 1 from procrastinate_jobs "
        "where queue_name = 'agent' and status in ('todo', 'doing')"
    )
    wait_for(lambda: not rows(open_jobs), what="jobs closed")
    time.sleep(1.5)  # nothing else may happen to it
    assert completions(tid) == 1
    assert rows("select count(*) from model_usage")[0][0] == 1
    assert rows("select status from external_effect") == [("done",)]
    assert rows("select count(*) from runs where status = 'succeeded'")[0][0] == 1
    assert rows("select count(*) from events where kind = 'run.output'")[0][0] == 1


def test_kill9_during_the_call_is_not_resent_until_the_founder_retries(start):
    tid = add()
    assert start(test_crash_point="during_call").exit_code() == -signal.SIGKILL
    start()
    wait_for(lambda: state(tid)[0] == "failed_execution", what="dead letter")
    assert state(tid)[1] == "effect_unknown" and completions(tid) == 0
    assert rows("select count(*) from model_usage")[0][0] == 1
    with Session(engine()) as s:
        effects.founder_retry(s, s.get(Task, tid), "founder")
    wait_for(lambda: state(tid)[0] == "completed", what="completion after retry")
    assert rows("select count(*) from model_usage")[0][0] == 2 and completions(tid) == 1


def test_external_kill9_mid_run_then_restart(start):
    tid = add()
    first = start(echo_seconds=30)
    wait_for(lambda: state(tid)[0] == "running", what="running")
    first.proc.kill()
    first.exit_code()
    assert state(tid)[0] == "running"  # nothing is falsely completed while the worker is dead
    start()
    wait_for(lambda: state(tid)[0] == "completed", what="completion")
    assert completions(tid) == 1 and rows("select count(*) from model_usage")[0][0] == 1


def test_at_most_two_run_at_once(start):
    ids = [add(f"t{i}") for i in range(5)]
    start(fake_delay_s=1)
    peak = 0

    def done():
        nonlocal peak
        peak = max(peak, rows("select count(*) from tasks where status = 'running'")[0][0])
        return all(state(i)[0] == "completed" for i in ids)

    wait_for(done, timeout=60, what="all complete")
    assert peak == 2


def test_emergency_stop_halts_within_five_seconds(start):
    a, b, c = add("a"), add("b"), add("c")
    worker = start(fake_delay_s=60)
    wait_for(lambda: len(children(worker.proc.pid)) == 2, what="two CLI children")
    kids = children(worker.proc.pid)
    began = time.monotonic()
    with Session(engine()) as s:
        assert control.request_stop(s, "founder", "stop test") == 2
    wait_for(lambda: not any(Path(f"/proc/{k}").exists() for k in kids), 5, "children gone")
    assert time.monotonic() - began < 5
    assert state(a) == state(b) == ("cancelled", "emergency stop: stop test")
    time.sleep(2)
    assert state(c)[0] == "ready" and not children(worker.proc.pid)
    assert rows("select count(*) from runs")[0][0] == 2
    assert worker.proc.poll() is None  # the worker itself stays up
    with Session(engine()) as s:
        control.resume(s, "founder")
    wait_for(lambda: state(c)[0] == "running", what="work after resume")


def test_stop_with_a_child_ignoring_sigterm_and_the_real_30s_grace(start):
    first, second = add("stubborn"), add("c")
    worker = start(fake_delay_s=120, fake_ignore_term=1, stop_grace_s=30, agent_concurrency=1)
    kids = wait_for(lambda: children(worker.proc.pid), what="CLI child")
    wait_for(lambda: ignores_sigterm(kids[0]), what="the child's TERM trap")
    began = time.monotonic()
    with Session(engine()) as s:
        control.request_stop(s, "founder", "stubborn")
    # within 5 s: the task is cancelled and nothing new starts, although the child survives
    assert time.monotonic() - began < 5 and state(first)[0] == "cancelled"
    time.sleep(5)
    assert state(second)[0] == "ready" and Path(f"/proc/{kids[0]}").exists()
    assert rows("select count(*) from runs")[0][0] == 1
    wait_for(lambda: not Path(f"/proc/{kids[0]}").exists(), 35, "SIGKILL after the grace period")
    assert 29 <= time.monotonic() - began < 40


def test_sigterm_exits_zero_and_hands_back_unsent_work(start):
    tid = add()
    worker = start(echo_seconds=30)
    wait_for(lambda: state(tid)[0] == "running", what="running")
    worker.proc.terminate()
    assert worker.exit_code() == 0, worker.log.read_text()
    assert state(tid)[0] == "ready"


def test_sigterm_during_a_call_dead_letters_it(start):
    tid = add()
    worker = start(fake_delay_s=60)
    wait_for(lambda: children(worker.proc.pid), what="CLI child")
    worker.proc.terminate()
    assert worker.exit_code() == 0, worker.log.read_text()
    assert state(tid) == ("failed_execution", "effect_unknown")


def test_lost_execution_makes_the_worker_exit_nonzero(start):
    add()
    worker = start(orphan_after_s=2)
    wait_for(lambda: "worker ready" in worker.log.read_text(), what="ready")
    other = add("orphan")
    with Session(engine()) as s:  # a running task nobody here is executing
        s.execute(text("update tasks set status = 'running' where id = :i"), {"i": other})
        s.execute(
            text(
                "insert into runs (id, created_at, schema_version, data_class, task_id, attempt,"
                " status, started_at) values ('r-orphan', now(), 1, 'public', :i, 1, 'running',"
                " now() - interval '1 minute')"
            ),
            {"i": other},
        )
        s.commit()
    assert worker.exit_code() == 1, worker.log.read_text()


def test_worker_waits_for_an_unreachable_database(tmp_path):
    w = Worker("postgresql+psycopg://u:p@127.0.0.1:1/none", tmp_path / "w.log")
    try:
        time.sleep(5)
        assert w.proc.poll() is None
    finally:
        w.stop()
