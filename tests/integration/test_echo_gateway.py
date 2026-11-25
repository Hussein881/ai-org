from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Task
from app.db.session import engine
from app.gateway.providers.fake import FakeProvider
from app.gateway.router import Gateway
from app.gateway.types import ProviderResponse, utcnow
from app.policy.model_policy import load_model_policy
from app.workers import echo
from tests.integration.test_api import _csrf


def gw(provs=None):
    policy = load_model_policy("config/model_policy.yaml")
    provs = provs or {n: FakeProvider(n) for n in policy.providers}
    return Gateway(sessionmaker(engine()), policy, provs, utcnow, lambda: False), provs


def new_task(client, title="hello"):
    return client.post("/api/tasks", json={"title": title}, headers=_csrf(client)).json()["id"]


def test_flag_off_keeps_the_echo(client):
    tid = new_task(client)
    with Session(engine()) as s:
        task, run = echo.claim_one(s)
        echo.finish(s, task, run)
    d = client.get(f"/api/tasks/{tid}").json()
    assert d["status"] == "completed"
    assert any(e["kind"] == "run.output" and e["payload"] == {"echo": "hello"} for e in d["events"])


def test_live_reply_uses_exactly_one_model_call_and_one_line(client):
    tid = new_task(client, "Plan the launch")
    g, provs = gw()
    provs["claude_cli"].script = [
        ProviderResponse("Got it, planning the launch now.\nextra line", 12, 8)
    ]
    with Session(engine()) as s:
        task, run = echo.claim_one(s)
        echo.finish(s, task, run, g)
    d = client.get(f"/api/tasks/{tid}").json()
    assert d["status"] == "completed"
    out = next(e for e in d["events"] if e["kind"] == "run.output")["payload"]
    assert out == {
        "reply": "Got it, planning the launch now.",
        "provider": "claude_cli",
        "model": "haiku",
        "source": "model",
    }
    assert len(provs["claude_cli"].calls) == 1 and provs["anthropic_api"].calls == []
    # the task text was founder_private and untrusted: delimited in the prompt
    assert "<untrusted_data>" in provs["claude_cli"].calls[0].prompt
    with Session(engine()) as s2:
        n = s2.execute(
            text("select count(*) from model_usage where role='ceo' and purpose='ack'")
        ).scalar()
    assert n == 1


def test_empty_model_reply_falls_back_without_a_second_call(client):
    new_task(client, "T")
    g, provs = gw()
    provs["claude_cli"].script = [ProviderResponse("   \n  ", 1, 1)]
    with Session(engine()) as s:
        task, run = echo.claim_one(s)
        echo.finish(s, task, run, g)
        assert s.get(Task, task.id).status == "completed"
    assert len(provs["claude_cli"].calls) == 1 and provs["anthropic_api"].calls == []


def test_queued_task_waits_on_its_own_retry_at_while_others_flow(client):
    from app.gateway.types import RateLimited

    t1 = new_task(client, "first")
    t2 = new_task(client, "second")
    g, provs = gw()
    soon = utcnow() + timedelta(hours=3)
    provs["claude_cli"].script = [RateLimited(soon)]
    provs["anthropic_api"].script = [RateLimited(soon)]
    with Session(engine()) as s:
        task, run = echo.claim_one(s)
        echo.finish(s, task, run, g)
    d = client.get(f"/api/tasks/{t1}").json()
    assert d["status"] == "ready"
    assert any(e["kind"] == "gateway.queued" for e in d["events"])
    assert client.get("/api/roles/ceo").json()["status"] == "idle"
    with Session(engine()) as s:  # the queued task is not claimable yet; the next one is
        nxt = echo.claim_one(s)
        assert nxt is not None and nxt[0].id == t2


def test_refused_data_class_fails_the_task_cleanly(client):
    from app.gateway.types import DataClassRefused

    tid = new_task(client, "x")

    class Refusing:
        def complete(self, *a, **k):
            raise DataClassRefused("no route")

    with Session(engine()) as s:
        task, run = echo.claim_one(s)
        echo.finish(s, task, run, Refusing())  # type: ignore[arg-type]
    d = client.get(f"/api/tasks/{tid}").json()
    assert d["status"] == "failed_execution"
    assert client.get("/api/roles/ceo").json()["status"] == "idle"


def test_cancel_during_live_call_is_respected(client):
    tid = new_task(client)
    g, provs = gw()
    h = _csrf(client)

    def cancel_then_reply(req):
        client.post(f"/api/tasks/{tid}/transition", json={"to": "cancelled"}, headers=h)
        return ProviderResponse("ok", 1, 1)

    provs["claude_cli"].script = [cancel_then_reply]
    with Session(engine()) as s:
        task, run = echo.claim_one(s)
        echo.finish(s, task, run, g)
    assert client.get(f"/api/tasks/{tid}").json()["status"] == "cancelled"
    assert client.get("/api/roles/ceo").json()["status"] == "idle"


def test_usage_api_and_role_detail(client):
    assert client.get("/api/usage").status_code == 401
    token = _csrf(client)
    body = client.get("/api/usage").json()
    names = [p["provider"] for p in body["providers"]]
    assert "fake" not in names and "openai_api" in names
    by = {p["provider"]: p for p in body["providers"]}
    assert by["openai_api"]["status"] == "disabled"
    assert by["claude_cli"]["status"] == "ok"
    assert (
        by["claude_cli"]["limits"][0]["used"] == 0 and by["claude_cli"]["limits"][0]["limit"] == 80
    )
    # a recorded call shows up in the gauge and in the role's calls-today
    new_task(client, "gauge")
    g, provs = gw()
    with Session(engine()) as s:
        task, run = echo.claim_one(s)
        echo.finish(s, task, run, g)
    by = {p["provider"]: p for p in client.get("/api/usage").json()["providers"]}
    assert by["claude_cli"]["limits"][0]["used"] == 1
    d = client.get("/api/roles/ceo").json()
    assert d["calls_today"] == 1 and d["route"] == "codex_cli / default"
    assert token  # session still valid


def test_superseded_run_cannot_complete_the_task(client):
    tid = new_task(client)
    g, provs = gw()

    def restart_during_call(req):
        with Session(engine()) as other:
            echo.reconcile(other)  # another process takes the task back
        return ProviderResponse("late reply", 1, 1)

    provs["claude_cli"].script = [restart_during_call]
    with Session(engine()) as s:
        task, run = echo.claim_one(s)
        echo.finish(s, task, run, g)
    d = client.get(f"/api/tasks/{tid}").json()
    assert d["status"] == "ready"
    assert not any(e["kind"] == "run.output" for e in d["events"])


def test_stored_outputs_are_redacted(client):
    planted = "sk-ant-" + "api03-PLANTED1234567890abcdef"
    tid = new_task(client, f"use {planted} now")
    with Session(engine()) as s:
        task, run = echo.claim_one(s)
        echo.finish(s, task, run)
    with Session(engine()) as s:
        blob = str(s.execute(text("select result from runs")).all())
        blob += str(s.execute(text("select payload from events where kind='run.output'")).all())
    assert planted not in blob
    assert client.get(f"/api/tasks/{tid}").json()["status"] == "completed"


def test_shipped_ack_route_is_a_single_haiku_attempt():
    policy = load_model_policy("config/model_policy.yaml")
    assert policy.route_for("ceo", "ack") == [("claude_cli", "haiku")]


def test_failed_ack_makes_no_second_or_paid_call(client):
    from app.gateway.types import ProviderError

    tid = new_task(client)
    g, provs = gw()
    provs["claude_cli"].script = [ProviderError("cli_error")]
    with Session(engine()) as s:
        task, run = echo.claim_one(s)
        echo.finish(s, task, run, g)
    assert client.get(f"/api/tasks/{tid}").json()["status"] == "failed_execution"
    assert len(provs["claude_cli"].calls) == 1 and provs["anthropic_api"].calls == []


def test_task_cancelled_before_dispatch_is_never_sent_to_a_model(client):
    tid = new_task(client)
    g, provs = gw()
    h = _csrf(client)
    with Session(engine()) as s:
        task, run = echo.claim_one(s)
        client.post(f"/api/tasks/{tid}/transition", json={"to": "cancelled"}, headers=h)
        echo.finish(s, task, run, g)
    assert provs["claude_cli"].calls == []
    assert client.get("/api/roles/ceo").json()["status"] == "idle"
