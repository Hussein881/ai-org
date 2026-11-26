"""S04 escalation repair: regression tests per finding in docs/state/plans/S04-findings.md and
the two open Codex items. Each failed before its fix (artifacts/review/S04-repair-red.txt)."""

import asyncio
import subprocess
import sys
import threading
import time
from datetime import timedelta
from pathlib import Path

import pytest
import yaml
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.core import control, effects, tasks
from app.db.session import engine
from app.gateway import ledger
from app.gateway.procs import REGISTRY, ProcRegistry
from app.gateway.providers.fake import FakeProvider
from app.gateway.router import Gateway
from app.gateway.types import (
    AllRoutesFailed,
    Halted,
    PromptPart,
    ProviderError,
    ProviderResponse,
    RateLimited,
    utcnow,
)
from app.policy.model_policy import ModelPolicy, load_model_policy
from app.workers import echo
from app.workers.supervisor import ControlWatcher
from tests.integration.test_api import _csrf
from tests.integration.test_echo_gateway import gw, new_task
from tests.integration.test_worker import dispatch, make_due, run_one, sql, status_of, supervisor

ROOT = Path(__file__).resolve().parents[2]


def fence_only_stop(reason="r"):
    """Phase one of a stop committed, phase two never ran (e.g. it hit lock_timeout)."""
    with Session(engine()) as s:
        s.execute(
            text(
                "update worker_control set stopped = true, generation = generation + 1, "
                "reason = :r where id = 1"
            ),
            {"r": reason},
        )
        s.commit()


def run_status(task_id):
    return [r[0] for r in sql("select status from runs where task_id = :t", t=task_id)]


def role_status(slug="ceo"):
    return sql("select status from roles where slug = :s", s=slug)[0][0]


# ---- H1: a stop whose second phase failed ---------------------------------------
def test_h1_reply_arriving_during_a_half_done_stop_cancels_instead_of_completing(client):
    tid = new_task(client)
    g, provs = gw()

    def stop_then_reply(req):
        fence_only_stop()
        return ProviderResponse("too late", 1, 1)

    provs["claude_cli"].script = [stop_then_reply]
    run_one(g)
    assert status_of(tid) == ("cancelled", "emergency stop: r")
    assert run_status(tid) == ["cancelled"]
    assert sql("select count(*) from events where kind = 'run.output'")[0][0] == 0
    assert role_status() == "idle"


@pytest.mark.parametrize("sent", [False, True])
def test_h1_halt_during_a_half_done_stop_cancels_instead_of_requeue_or_dead_letter(
    client, monkeypatch, sent
):
    tid = new_task(client)

    def halted_reply(db, task, run, gateway):
        fence_only_stop()
        raise Halted(sent=sent)

    monkeypatch.setattr(echo, "live_reply", halted_reply)
    run_one(gw()[0])
    assert status_of(tid) == ("cancelled", "emergency stop: r")
    with Session(engine()) as s:
        assert effects.latest(s, tid, effects.MODEL_ACK).status == ("unknown" if sent else "failed")
    make_due(tid)
    with Session(engine()) as s:
        control.resume(s, "t")
        assert echo.claim_one(s) is None  # nothing escaped the stop


def test_h1_live_worker_finishes_a_stop_whose_second_phase_failed(client):
    tid = new_task(client)
    with Session(engine()) as s:
        echo.claim_one(s)
    fence_only_stop()
    sup, _ = supervisor()
    sup.active[tid] = time.monotonic()  # it is being executed right now
    with Session(engine()) as s:
        assert sup.health(s) == ""
    assert status_of(tid) == ("cancelled", "emergency stop: r")
    assert run_status(tid) == ["cancelled"]


def test_h1_aiorgctl_reports_a_failed_second_phase_without_a_traceback(client, monkeypatch, capsys):
    from app import ctl

    def busy(*a, **k):
        raise OperationalError("lock timeout", {}, Exception("lock timeout"))

    monkeypatch.setattr(control, "cancel_for_stop", busy)
    assert ctl.main(["stop", "--reason", "x"]) == 0
    out = capsys.readouterr().out
    assert "stopped" in out and "worker" in out
    with Session(engine()) as s:
        assert control.get(s).stopped


# ---- H2: the stop-flag watcher can fail for good --------------------------------
def test_h2_control_reader_survives_unexpected_errors(db_url):
    registry = ProcRegistry()
    watcher = ControlWatcher(db_url, registry, 1, poll_s=0.05)
    real, calls = watcher.apply, []

    def flaky(stopped, generation):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("unexpected")
        real(stopped, generation)

    watcher.apply = flaky  # type: ignore[method-assign]
    watcher.start()
    try:
        t0 = watcher.last_ok
        deadline = time.monotonic() + 3
        while watcher.last_ok == t0 and time.monotonic() < deadline:
            time.sleep(0.05)
        assert watcher.last_ok > t0 and len(calls) >= 2
        assert watcher.stale_for() < 1
    finally:
        watcher.close()


def test_h2_missing_control_row_counts_as_unreadable(db_url):
    with Session(engine()) as s:
        s.execute(text("delete from worker_control"))
        s.commit()
    watcher = ControlWatcher(db_url, ProcRegistry(), 1, poll_s=0.05)
    watcher.last_ok = time.monotonic() - 100
    try:
        watcher._read_once()
        assert watcher.stale_for() > 50
    finally:
        watcher.close()


def test_h2_supervisor_restarts_when_the_stop_flag_stays_unreadable(client):
    sup, _ = supervisor()
    sup.control_stale = lambda: 11.0
    stop = asyncio.Event()

    async def go():
        async with sup.app.open_async():
            return await asyncio.wait_for(sup.run(stop), 10)

    reason = asyncio.run(go())
    assert "stop flag" in reason


# ---- M1: single-task cancel -----------------------------------------------------
def test_m1_single_task_cancel_closes_the_run_and_frees_the_role(client):
    tid = new_task(client)
    with Session(engine()) as s:
        echo.claim_one(s)
    r = client.post(f"/api/tasks/{tid}/transition", json={"to": "cancelled"}, headers=_csrf(client))
    assert r.status_code == 200
    assert run_status(tid) == ["cancelled"]
    assert role_status() == "idle"


def test_m1_cancelled_task_has_its_cli_killed(client):
    tid = new_task(client)
    with Session(engine()) as s:
        echo.claim_one(s)
    registry = ProcRegistry()
    sup, _ = supervisor(registry=registry)
    sup.active[tid] = time.monotonic()
    with registry.owner(tid):
        proc = registry.spawn(["sleep", "30"], stdout=subprocess.DEVNULL, text=True)
    client.post(f"/api/tasks/{tid}/transition", json={"to": "cancelled"}, headers=_csrf(client))
    with Session(engine()) as s:
        sup.health(s)
    assert proc.wait(timeout=5) != 0
    assert registry.forget(proc) is True  # reported as killed, so the call is not trusted


# ---- M2: founder Retry starts a fresh budget ------------------------------------
def test_m2_founder_retry_resets_the_transient_budget(client):
    tid = new_task(client)
    g, provs = gw()
    provs["claude_cli"].script = [ProviderError("http_503") for _ in range(4)]
    for _ in range(2):
        run_one(g)
        make_due(tid)
    run_one(g)
    assert status_of(tid)[0] == "failed_execution"
    assert (
        client.post(f"/api/admin/dead-letter/{tid}/retry", headers=_csrf(client)).status_code == 204
    )
    run_one(g)
    assert status_of(tid)[0] == "ready"  # a fresh transient retry, not an instant dead-letter


def test_m2_founder_retry_resets_the_crash_count(client):
    tid = new_task(client)
    for _ in range(3):
        with Session(engine()) as s:
            echo.claim_one(s)
            echo.reconcile(s)
    assert status_of(tid) == ("failed_execution", "crash_loop")
    assert (
        client.post(f"/api/admin/dead-letter/{tid}/retry", headers=_csrf(client)).status_code == 204
    )
    with Session(engine()) as s:
        echo.claim_one(s)
        echo.reconcile(s)
    assert status_of(tid)[0] == "ready"


# ---- M3: role status under concurrency ------------------------------------------
def test_m3_role_cannot_show_idle_while_a_task_is_running(client, monkeypatch):
    first, second = new_task(client, "a"), new_task(client, "b")
    with Session(engine()) as s:
        assert echo.claim_one(s, task_id=first) is not None
    assert role_status() == "working"
    paused, go, b_done = threading.Event(), threading.Event(), threading.Event()
    real = tasks.transition

    def slow_transition(db, task, target, **kw):
        if target == "running" and threading.current_thread().name == "claimer":
            paused.set()
            go.wait(5)
        return real(db, task, target, **kw)

    monkeypatch.setattr(tasks, "transition", slow_transition)

    def claim():
        with Session(engine()) as s:
            echo.claim_one(s, task_id=second)

    def finish_first():
        with Session(engine()) as s:  # the first task's run ends while the second is claimed
            control.set_idle_if_free(s, "ceo", first)
            s.commit()
        b_done.set()

    a = threading.Thread(target=claim, name="claimer")
    a.start()
    assert paused.wait(5)
    b = threading.Thread(target=finish_first)
    b.start()
    b_done.wait(1)
    go.set()
    a.join(10)
    b.join(10)
    assert status_of(second)[0] == "running"
    assert role_status() == "working"


# ---- M4: orphan check snapshot ---------------------------------------------------
def test_m4_task_finishing_during_the_orphan_query_is_not_an_orphan(client):
    tid = new_task(client)
    with Session(engine()) as s:
        echo.claim_one(s)
        s.execute(text("update runs set started_at = now() - interval '5 minutes'"))
        s.commit()
    sup, _ = supervisor()
    sup.active[tid] = 0
    with Session(engine()) as s:
        real = s.scalars

        def scalars_then_finish(*a, **k):
            out = list(real(*a, **k))
            sup.active.pop(tid, None)  # the run ends right after the query
            return out

        s.scalars = scalars_then_finish  # type: ignore[method-assign]
        assert sup.orphans(s, 0) == []


# ---- M5: a job stuck in `doing` while the worker lives ---------------------------
def test_m5_stuck_doing_job_is_released_live(client):
    tid = new_task(client)
    sup, app = supervisor()
    assert dispatch(sup, app) == 1
    with Session(engine()) as s:
        s.execute(text("update procrastinate_jobs set status = 'doing'"))
        s.commit()
    with Session(engine()) as s:
        sup.active[tid] = 0
        assert sup.release_stuck_jobs(s, 0.0) == 0
        assert sup.release_stuck_jobs(s, 100.0) == 0  # executing: never touched
        sup.active.pop(tid)
        assert sup.release_stuck_jobs(s, 200.0) == 0  # first sighting
        assert sup.release_stuck_jobs(s, 205.0) == 0  # not long enough
        assert sup.release_stuck_jobs(s, 211.0) == 1
    assert dispatch(sup, app) == 1


# ---- M6, lows: what counts as sent -----------------------------------------------
@pytest.mark.parametrize("provider", ["claude", "codex"])
def test_m6_failing_env_precheck_is_not_sent(monkeypatch, provider):
    from app.gateway.providers import live
    from app.gateway.types import ProviderRequest

    def killed():
        raise ProviderError("killed")

    monkeypatch.setattr(live, "env_is_clean", killed)
    prov = live.ClaudeCli() if provider == "claude" else live.CodexCli()
    with pytest.raises(ProviderError) as e:
        prov.call(ProviderRequest(model="haiku", prompt="x"))
    assert e.value.not_sent


def _two_step(db_url, mutate=None):
    d = yaml.safe_load((ROOT / "config/model_policy.yaml").read_text())
    d["routes"]["duo"] = ["claude_cli:haiku", "anthropic_api:claude-haiku-5-5"]
    if mutate:
        mutate(d)
    provs = {n: FakeProvider(n) for n in d["providers"]}
    flag = [False]
    g = Gateway(
        sessionmaker(engine()),
        ModelPolicy.model_validate(d),
        provs,
        utcnow,
        lambda: False,
        halted=lambda: flag[0],
    )
    return g, provs, flag


def test_m6_halt_after_a_not_sent_failure_is_not_sent(db_url):
    g, provs, flag = _two_step(db_url)

    def halt_unsent(req):
        flag[0] = True
        raise ProviderError("killed", not_sent=True)

    provs["claude_cli"].script = [halt_unsent]
    with pytest.raises(Halted) as e:
        g.complete("duo", None, [PromptPart("task", "x")], None, "public")
    assert e.value.sent is False


def test_low_not_sent_failure_then_halt_is_not_sent(db_url):
    g, provs, _ = _two_step(db_url)
    provs["claude_cli"].script = [ProviderError("network", not_sent=True)]
    checks = iter([False, False, True])  # the stop lands after the first attempt
    with pytest.raises(Halted) as e:
        g.complete(
            "duo", None, [PromptPart("task", "x")], None, "public", cancelled=lambda: next(checks)
        )
    assert e.value.sent is False


def test_low_in_attempt_halt_gate_keeps_an_earlier_maybe_sent(db_url):
    g, provs, _ = _two_step(db_url)
    provs["claude_cli"].script = [ProviderError("timeout")]
    checks = iter([False, False, False, True])  # loop, gate, loop, then the second gate
    with pytest.raises(Halted) as e:
        g.complete(
            "duo", None, [PromptPart("task", "x")], None, "public", cancelled=lambda: next(checks)
        )
    assert e.value.sent is True


def test_low_calls_never_sent_do_not_use_call_limits(db_url):
    g, provs, _ = _two_step(db_url)
    provs["claude_cli"].script = [ProviderError("network", not_sent=True)]
    checks = iter([False, False, False, True])
    with pytest.raises(Halted):
        g.complete(
            "duo", None, [PromptPart("task", "x")], None, "public", cancelled=lambda: next(checks)
        )
    assert sql("select count(*) from model_usage")[0][0] == 2  # both reservations are on record
    policy = load_model_policy("config/model_policy.yaml")
    with Session(engine()) as s:
        for name in ("claude_cli", "anthropic_api"):
            for lim in policy.providers[name].limits:
                assert ledger.window_usage(s, name, lim, utcnow(), policy).used == 0


# ---- M7: rate-limit reset bounds ---------------------------------------------------
def test_m7_rate_limit_reset_is_clamped(db_url):
    now = utcnow()
    with Session(engine()) as s:
        past = ledger.mark_rate_limited(s, "gemini_api", now - timedelta(hours=1), now)
        far = ledger.mark_rate_limited(s, "openrouter_free", now + timedelta(days=400), now)
    assert past >= now + timedelta(seconds=60)
    assert far <= now + timedelta(hours=24)


# ---- M8: ambiguous failures warn before Retry --------------------------------------
@pytest.mark.parametrize(
    ("err", "reason", "effect"),
    [
        (ProviderError("timeout"), "call_maybe_sent", "unknown"),
        (ProviderError("network"), "call_maybe_sent", "unknown"),
        (ProviderError("http_400"), "AllRoutesFailed", "failed"),
    ],
)
def test_m8_ambiguous_failure_is_marked_may_have_been_sent(client, err, reason, effect):
    tid = new_task(client)
    g, provs = gw()
    provs["claude_cli"].script = [err]
    run_one(g)
    assert status_of(tid) == ("failed_execution", reason)
    with Session(engine()) as s:
        assert effects.latest(s, tid, effects.MODEL_ACK).status == effect


def test_m8_router_reports_maybe_sent(db_url):
    g, provs, _ = _two_step(db_url)
    provs["claude_cli"].script = [ProviderError("http_503")]
    provs["anthropic_api"].script = [ProviderError("timeout")]
    with pytest.raises(AllRoutesFailed) as e:
        g.complete("duo", None, [PromptPart("task", "x")], None, "public")
    assert e.value.maybe_sent and not e.value.retryable


# ---- M9: waiting tasks say so ------------------------------------------------------
def test_m9_waiting_task_shows_why_and_until_when(client):
    first = new_task(client)
    g, provs = gw()
    provs["claude_cli"].script = [ProviderError("http_503")]
    run_one(g)
    assert status_of(first) == ("ready", "retry_transient")
    tid = new_task(client, "b")
    provs["claude_cli"].script = [RateLimited(utcnow() + timedelta(minutes=30))]
    with Session(engine()) as s:
        echo.finish(s, *echo.claim_one(s, task_id=tid), g)
    d = client.get(f"/api/tasks/{tid}").json()
    assert (d["status"], d["status_reason"]) == ("ready", "waiting_quota")
    assert d["retry_at"] is not None
    assert all(t["retry_at"] is not None for t in client.get("/api/tasks").json())


# ---- M10: logs say what happened ---------------------------------------------------
def test_m10_skipped_routes_are_logged(db_url, caplog):
    g, provs, _ = _two_step(db_url)
    provs["claude_cli"].is_available = False
    with caplog.at_level("INFO", logger="aiorg.gateway"):
        g.complete("duo", None, [PromptPart("task", "x")], None, "public")
    assert "claude_cli" in caplog.text and "not available" in caplog.text


def test_m10_restart_reason_keeps_the_message_but_no_secret(monkeypatch):
    from app.workers.host import describe

    monkeypatch.setenv("AIORG_TEST_PASSWORD", "hunter2-very-secret")
    text_ = describe(RuntimeError("db said no: password=hunter2-very-secret"))
    assert text_.startswith("RuntimeError: db said no")
    assert "hunter2-very-secret" not in text_


# ---- M11: echo --once honours a stop -----------------------------------------------
def test_m11_echo_once_watches_the_stop_flag(client, monkeypatch, capsys):
    import app.gateway.factory as factory
    import app.workers.supervisor as sup_mod

    seen: dict[str, object] = {}

    class FakeWatcher:
        def __init__(self, url, registry, grace_s, **kw):
            seen["registry"] = registry

        def start(self):
            seen["started"] = True

        def close(self):
            seen["closed"] = True

    def fake_build(halted=lambda: False):
        seen["halted"] = halted
        return gw()[0]

    monkeypatch.setattr(sup_mod, "ControlWatcher", FakeWatcher)
    monkeypatch.setattr(factory, "build_gateway", fake_build)
    monkeypatch.setattr(sys, "argv", ["echo", "--once"])
    tid = new_task(client)
    echo.main()
    assert f"task {tid} -> completed" in capsys.readouterr().out
    assert seen["registry"] is REGISTRY and seen["started"] and seen["closed"]
    assert seen["halted"] == REGISTRY.halted


# ---- Codex open item 1: claim after a shutdown halt --------------------------------
def test_codex1_halt_landing_during_the_claim_claims_nothing(client, monkeypatch):
    tid = new_task(client)
    registry = ProcRegistry()
    sup, _ = supervisor(registry=registry)
    real = tasks.set_role_status

    def halt_mid_claim(db, slug, status, task_id=None):
        if status == "working":
            registry.close(1)  # shutdown arrives after work()'s own check, inside the claim
        return real(db, slug, status, task_id)

    monkeypatch.setattr(tasks, "set_role_status", halt_mid_claim)
    sup.work(tid)
    assert status_of(tid)[0] == "ready"
    assert sql("select count(*) from runs")[0][0] == 0


# ---- Codex open item 2: lock loss must not wait for a hung spawn -------------------
def test_codex2_lock_loss_exits_even_while_a_spawn_holds_the_registry_lock():
    from app.workers.host import on_lock_lost

    registry = ProcRegistry()
    proc = registry.spawn(["sleep", "30"], stdout=subprocess.DEVNULL, text=True)
    held, release = threading.Event(), threading.Event()

    def hung_spawn():
        with registry._mu:
            held.set()
            release.wait(10)

    t = threading.Thread(target=hung_spawn)
    t.start()
    assert held.wait(2)
    codes: list[int] = []
    started = time.monotonic()
    try:
        on_lock_lost(registry, codes.append)
        assert time.monotonic() - started < 1 and codes == [1]
        assert registry.halted()
        assert proc.wait(timeout=5) == -9
    finally:
        release.set()
        t.join(5)
    with pytest.raises(ProviderError):
        registry.spawn(["true"])


# ---- lows -------------------------------------------------------------------------
def test_low_gateway_host_launcher_reads_only_the_db_password():
    launcher = (ROOT / "scripts/gateway-host.sh").read_text()
    assert "set -a" not in launcher and ". ./.env" not in launcher
    assert ". scripts/host-env.sh" in launcher


def test_low_procrastinate_is_pinned_to_the_vendored_schema():
    pyproject = (ROOT / "pyproject.toml").read_text()
    assert '"procrastinate==3.12.0"' in pyproject
    assert (ROOT / "migrations/procrastinate/schema-3.12.0.sql").exists()


def test_low_role_with_an_empty_route_shows_no_route(client, tmp_path, monkeypatch):
    d = yaml.safe_load((ROOT / "config/model_policy.yaml").read_text())
    d["routes"]["ceo"] = []
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(d))
    monkeypatch.setenv("AIORG_MODEL_POLICY_PATH", str(path))
    _csrf(client)
    r = client.get("/api/roles/ceo")
    assert r.status_code == 200 and r.json()["route"] == "no route"


def test_low_calls_today_starts_at_midnight_in_day_tz():
    from datetime import UTC, datetime

    from app.api.roles import day_start

    now = datetime(2026, 11, 26, 3, 0, tzinfo=UTC)
    assert day_start(now, "UTC") == datetime(2026, 11, 26, tzinfo=UTC)
    assert day_start(now, "America/New_York") == datetime(2026, 11, 25, 5, 0, tzinfo=UTC)
