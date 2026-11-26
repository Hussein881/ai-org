"""S04: dispatch, effects, retries, recovery, stop and the admin API (no worker process)."""

import asyncio
import threading
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core import control, effects
from app.db.models import ExternalEffect, Run, Task, WorkerStatus
from app.db.session import engine
from app.gateway.procs import ProcRegistry
from app.gateway.types import ProviderError, ProviderResponse, utcnow
from app.workers import echo, queue
from app.workers.lock import ExecutorLock
from app.workers.supervisor import ControlWatcher, Supervisor, clear_dead_jobs, guard_lock
from tests.integration.test_api import _csrf
from tests.integration.test_echo_gateway import gw, new_task


def sql(query, **params):
    with Session(engine()) as s:
        return s.execute(text(query), params).all()


def status_of(task_id):
    with Session(engine()) as s:
        t = s.get(Task, task_id)
        return t.status, t.status_reason


def supervisor(free_mb=4096, registry=None):
    app = queue.make_app(get_settings().database_url)
    sup = Supervisor(
        get_settings(), engine(), app, None, 0, registry or ProcRegistry(), lambda: free_mb
    )
    return sup, app


def dispatch(sup, app):
    async def go():
        async with app.open_async():
            return await sup.dispatch()

    return asyncio.run(go())


def run_one(g=None):
    with Session(engine()) as s:
        claimed = echo.claim_one(s)
        assert claimed is not None
        echo.finish(s, *claimed, g)


def make_due(task_id):
    with Session(engine()) as s:
        s.get(Task, task_id).retry_at = utcnow() - timedelta(seconds=1)
        s.commit()


# ---- dispatch ------------------------------------------------------------------
def test_dispatch_caps_at_two_and_never_duplicates_a_job(client):
    ids = [new_task(client, f"t{i}") for i in range(4)]
    sup, app = supervisor()
    assert dispatch(sup, app) == 2
    assert dispatch(sup, app) == 0
    rows = sql("select lock, queueing_lock from procrastinate_jobs order by id")
    assert [r.lock for r in rows] == [f"task:{i}" for i in ids[:2]]
    assert all(r.lock == r.queueing_lock for r in rows)


def test_dispatch_waits_for_retry_at_and_respects_stop_ram_and_halt(client):
    tid = new_task(client)
    with Session(engine()) as s:
        s.get(Task, tid).retry_at = utcnow() + timedelta(hours=1)
        s.commit()
    sup, app = supervisor()
    assert dispatch(sup, app) == 0
    make_due(tid)
    low, low_app = supervisor(free_mb=100)
    assert dispatch(low, low_app) == 0
    halted = ProcRegistry()
    halted.halt(1)
    h, h_app = supervisor(registry=halted)
    assert dispatch(h, h_app) == 0
    with Session(engine()) as s:
        control.request_stop(s, "t", "test")
    assert dispatch(sup, app) == 0
    with Session(engine()) as s:
        control.resume(s, "t")
    assert dispatch(sup, app) == 1


def test_dead_jobs_are_closed_and_their_lock_freed(client):
    new_task(client)
    sup, app = supervisor()
    assert dispatch(sup, app) == 1
    with Session(engine()) as s:  # simulate a worker that died while holding the job
        s.execute(text("update procrastinate_jobs set status = 'doing'"))
        s.commit()
    assert dispatch(sup, app) == 0
    with Session(engine()) as s:
        assert clear_dead_jobs(s) == 1
    assert dispatch(sup, app) == 1


def test_orphan_detection_and_heartbeat(client):
    tid = new_task(client)
    with Session(engine()) as s:
        echo.claim_one(s)
        s.execute(text("update runs set started_at = now() - interval '5 minutes'"))
        s.commit()
    sup, _ = supervisor()
    with Session(engine()) as s:
        assert sup.orphans(s, 0) == [tid]
        sup.active[tid] = 0
        assert sup.orphans(s, 0) == []
        sup.beat(s)
        assert s.get(WorkerStatus, 1).in_flight == 1
    client.cookies.clear()
    assert client.get("/api/admin/status").status_code == 401
    _csrf(client)
    assert client.get("/api/admin/status").json()["worker_alive"] is True
    with Session(engine()) as s:
        s.get(WorkerStatus, 1).heartbeat_at = utcnow() - timedelta(seconds=30)
        s.commit()
    assert client.get("/api/admin/status").json()["worker_alive"] is False


# ---- single executor -----------------------------------------------------------
def test_only_one_executor_holds_the_lock(client):
    a, b = ExecutorLock(engine()), ExecutorLock(engine())
    assert a.acquire() and a.alive()
    assert not b.acquire()
    a.release()
    assert not a.alive()
    assert b.acquire()
    b.release()


def test_claim_is_fenced_by_epoch_and_stop(client):
    new_task(client)
    with Session(engine()) as s:
        old = control.bump_epoch(s)
        new = control.bump_epoch(s)
        assert echo.claim_one(s, epoch=old) is None
        control.request_stop(s, "t", "x")
        assert echo.claim_one(s, epoch=new) is None
        control.resume(s, "t")
        assert echo.claim_one(s, epoch=new) is not None


# ---- retries and effects -------------------------------------------------------
def test_transient_errors_retry_twice_with_backoff_then_dead_letter(client):
    tid = new_task(client)
    g, provs = gw()
    provs["claude_cli"].script = [ProviderError("http_503") for _ in range(3)]
    delays = []
    for _ in range(2):
        before = utcnow()
        run_one(g)
        assert status_of(tid)[0] == "ready"
        with Session(engine()) as s:
            delays.append((s.get(Task, tid).retry_at - before).total_seconds())
            assert echo.claim_one(s) is None  # backing off
        make_due(tid)
    assert 8 < delays[0] < 15 and 55 < delays[1] < 70
    run_one(g)
    assert status_of(tid) == ("failed_execution", "AllRoutesFailed")
    assert len(provs["claude_cli"].calls) == 3


@pytest.mark.parametrize("kind", ["timeout", "cli_error", "network", "http_400"])
def test_ambiguous_or_permanent_errors_are_not_retried(client, kind):
    tid = new_task(client)
    g, provs = gw()
    provs["claude_cli"].script = [ProviderError(kind)]
    run_one(g)
    assert status_of(tid)[0] == "failed_execution"
    assert len(provs["claude_cli"].calls) == 1


def test_connect_failure_before_sending_is_retried(client):
    tid = new_task(client)
    g, provs = gw()
    provs["claude_cli"].script = [ProviderError("network", not_sent=True)]
    run_one(g)
    assert status_of(tid)[0] == "ready"


def _leave_effect(tid, state, result=None):
    """A run that died after writing an effect in `state`."""
    with Session(engine()) as s:
        task, run = echo.claim_one(s)
        eff = effects.begin(s, tid, run.id, effects.MODEL_ACK)
        if state != "intent":
            effects.resolve(s, eff.id, state, result)
        s.commit()
        echo.reconcile(s)


def test_unknown_outcome_is_never_resent_without_the_founder(client):
    tid = new_task(client)
    _leave_effect(tid, "intent")
    g, provs = gw()
    run_one(g)
    assert status_of(tid) == ("failed_execution", "effect_unknown")
    assert provs["claude_cli"].calls == []
    client.cookies.clear()
    assert client.get("/api/admin/dead-letter").status_code == 401
    h = _csrf(client)
    row = client.get("/api/admin/dead-letter").json()[0]
    assert (row["id"], row["reason"], row["attempts"]) == (tid, "effect_unknown", 2)
    assert client.post(f"/api/admin/dead-letter/{tid}/retry").status_code == 403  # no CSRF
    assert client.post(f"/api/admin/dead-letter/{tid}/retry", headers=h).status_code == 204
    assert client.post(f"/api/admin/dead-letter/{tid}/retry", headers=h).status_code == 409
    run_one(g)
    assert status_of(tid)[0] == "completed" and len(provs["claude_cli"].calls) == 1
    keys = [r[0] for r in sql("select idempotency_key from external_effect order by attempt")]
    assert keys == [f"{tid}:model_ack#1", f"{tid}:model_ack#2"]
    assert sql("select count(*) from audit_log where action = 'task.retry'")[0][0] == 1


def test_task_transition_endpoint_records_the_same_retry(client):
    tid = new_task(client)
    _leave_effect(tid, "intent")
    run_one(gw()[0])
    h = _csrf(client)
    r = client.post(f"/api/tasks/{tid}/transition", json={"to": "ready"}, headers=h)
    assert r.status_code == 200 and r.json()["status_reason"] is None
    with Session(engine()) as s:
        assert effects.latest(s, tid, effects.MODEL_ACK).status == "superseded"


def test_saved_reply_is_reused_without_a_second_call(client):
    tid = new_task(client)
    _leave_effect(tid, "done", {"reply": "saved earlier", "source": "model"})
    g, provs = gw()
    run_one(g)
    assert status_of(tid)[0] == "completed" and provs["claude_cli"].calls == []
    with Session(engine()) as s:
        assert s.query(ExternalEffect).count() == 1


def test_successful_call_leaves_one_done_effect(client):
    new_task(client)
    g, provs = gw()
    provs["claude_cli"].script = [ProviderResponse("On it.", 1, 1)]
    run_one(g)
    assert [r[0] for r in sql("select status from external_effect")] == ["done"]


def test_repeated_crashes_end_in_dead_letter(client):
    tid = new_task(client)
    for expected in ("ready", "ready", "failed_execution"):
        with Session(engine()) as s:
            assert echo.claim_one(s) is not None
            echo.reconcile(s)
        assert status_of(tid)[0] == expected
    assert status_of(tid)[1] == "crash_loop"


# ---- emergency stop ------------------------------------------------------------
def test_stop_cancels_running_work_with_a_reason_and_blocks_late_writes(client):
    first, second = new_task(client, "a"), new_task(client, "b")
    g, provs = gw()
    h = _csrf(client)

    def stop_during_call(req):
        r = client.post("/api/admin/stop", json={"reason": "halt now"}, headers=h)
        assert r.status_code == 200 and r.json()["stopped"] is True
        return ProviderResponse("too late", 1, 1)

    provs["claude_cli"].script = [stop_during_call]
    run_one(g)
    assert status_of(first) == ("cancelled", "emergency stop: halt now")
    assert status_of(second)[0] == "ready"
    assert sql("select count(*) from events where kind = 'run.output'")[0][0] == 0
    assert [r[0] for r in sql("select status from runs")] == ["cancelled"]
    assert client.get("/api/roles/ceo").json()["status"] == "idle"
    with Session(engine()) as s:
        assert echo.claim_one(s) is None
    assert client.post("/api/admin/stop", json={}, headers=h).json()["stop_reason"] == "halt now"
    assert client.post("/api/admin/resume", headers=h).json()["stopped"] is False
    with Session(engine()) as s:
        assert echo.claim_one(s)[0].id == second


def test_stop_needs_login_and_csrf(client):
    client.cookies.clear()
    assert client.post("/api/admin/stop", json={}).status_code == 401
    _csrf(client)
    assert client.post("/api/admin/stop", json={}).status_code == 403
    assert client.post("/api/admin/resume").status_code == 403


def test_recovery_finishes_a_half_done_stop(client):
    tid = new_task(client)
    with Session(engine()) as s:
        echo.claim_one(s)
        s.execute(text("update worker_control set stopped = true, generation = 1, reason = 'r'"))
        s.commit()
        echo.reconcile(s)
    assert status_of(tid) == ("cancelled", "emergency stop: r")
    with Session(engine()) as s:
        assert s.query(Run).filter(Run.status == "running").count() == 0


def test_watcher_acts_on_a_stop_even_after_a_quick_resume():
    registry = ProcRegistry()
    calls = []
    registry.halt = lambda grace: calls.append(grace)  # type: ignore[method-assign,assignment]
    watcher = ControlWatcher("postgresql://unused", registry, 30)
    watcher.apply(False, 0)
    assert calls == []
    watcher.apply(False, 1)  # stopped and resumed between two polls
    assert calls == [30]


def test_ctl_stop_and_resume(client, capsys):
    from app import ctl

    tid = new_task(client)
    with Session(engine()) as s:
        echo.claim_one(s)
    assert ctl.main(["stop", "--reason", "cli"]) == 0
    assert status_of(tid) == ("cancelled", "emergency stop: cli")
    assert ctl.main(["status"]) == 0 and ctl.main(["resume"]) == 0
    assert "stopped=True reason=cli" in capsys.readouterr().out


def test_service_launcher_can_find_the_clis_and_keeps_dotenv_secrets_out():
    launcher = Path("scripts/run-worker.sh").read_text()
    assert 'export PATH="$HOME/.local/bin:$PATH"' in launcher  # systemd's PATH lacks it
    assert "set -a" not in launcher and ". ./.env" not in launcher
    assert "POSTGRES_PASSWORD" in Path("scripts/host-env.sh").read_text()


# ---- Codex result review regressions -------------------------------------------
def test_run_cancelled_by_stop_then_resume_never_sends(client, monkeypatch):
    tid = new_task(client)
    g, provs = gw()
    real = echo.live_reply

    def stop_and_resume_first(db, task, run, gateway):
        with Session(engine()) as other:  # after the intent is committed, before the send
            control.request_stop(other, "t", "blip")
            control.resume(other, "t")
        return real(db, task, run, gateway)

    monkeypatch.setattr(echo, "live_reply", stop_and_resume_first)
    run_one(g)
    assert provs["claude_cli"].calls == [] and provs["anthropic_api"].calls == []
    assert status_of(tid)[0] == "cancelled"
    assert sql("select count(*) from model_usage where outcome = 'ok'")[0][0] == 0


def test_late_second_phase_of_a_resumed_stop_leaves_new_work_alone(client):
    tid = new_task(client)
    with Session(engine()) as s:
        control.request_stop(s, "t", "first")
        old = control.get(s).generation
        control.resume(s, "t")
        echo.claim_one(s)
        assert control.cancel_for_stop(s, old, "t", "first") == 0
        control.request_stop(s, "t", "second")
        control.resume(s, "t")
        assert control.cancel_for_stop(s, old, "t", "first") == 0
    assert status_of(tid) == ("cancelled", "emergency stop: second")


@pytest.mark.parametrize(
    ("state", "expected"),
    [("intent", ("failed_execution", "effect_unknown")), ("done", ("completed", None))],
)
def test_echo_mode_still_honours_effects(client, state, expected):
    tid = new_task(client)
    _leave_effect(tid, state, {"reply": "saved"} if state == "done" else None)
    run_one(None)  # live replies off
    assert status_of(tid) == expected
    if state == "done":
        payloads = sql("select payload->>'reply' from events where kind = 'run.output'")
        assert [r[0] for r in payloads] == ["saved"]


def test_losing_the_executor_lock_is_noticed_by_its_own_thread():
    lost = threading.Event()
    holding = [True]
    guard = guard_lock(lambda: holding[0], lost.set, every_s=0.05)
    assert not lost.wait(0.3)
    holding[0] = False
    assert lost.wait(2)
    guard.set()


def test_a_job_accepted_just_before_shutdown_claims_nothing(client):
    tid = new_task(client)
    registry = ProcRegistry()
    sup, _ = supervisor(registry=registry)
    registry.close(1)
    sup.work(tid)
    assert status_of(tid)[0] == "ready"
    assert sql("select count(*) from runs")[0][0] == 0
