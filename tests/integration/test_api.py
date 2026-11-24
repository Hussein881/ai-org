import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.db.session import engine
from tests.integration.conftest import alembic

H = {"X-Requested-With": "aiorg"}


def login(client, pw="pw-correct"):
    return client.post("/api/auth/login", json={"email": "f@x.io", "password": pw}, headers=H)


def test_unauthenticated_is_denied(client):
    assert client.get("/api/roles").status_code == 401
    assert client.get("/api/roles/ceo").status_code == 401
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/health").status_code == 200


def test_bad_login_rejected_and_audited(client):
    assert login(client, "nope").status_code == 401
    other = {"email": "no@x.io", "password": "x"}
    assert client.post("/api/auth/login", json=other, headers=H).status_code == 401
    with Session(engine()) as s:
        n = s.execute(text("select count(*) from events where kind='auth.login_failed'")).scalar()
    assert n == 2


def test_login_requires_custom_header(client):
    r = client.post("/api/auth/login", json={"email": "f@x.io", "password": "pw-correct"})
    assert r.status_code == 403


def test_cookie_flags_and_roles(client):
    r = login(client)
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    roles = client.get("/api/roles").json()
    assert {x["slug"] for x in roles} >= {"ceo", "board-advisor", "chief-of-staff", "qa"}
    assert all(x["status"] == "idle" for x in roles)
    assert client.get("/api/roles/ceo").json()["responsibilities"]
    assert client.get("/api/roles/missing").status_code == 404


def test_csrf_required_on_mutation(client):
    token = login(client).json()["csrf_token"]
    assert client.post("/api/auth/logout").status_code == 403
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": token}).status_code == 204


def test_tampered_cookie_rejected(client):
    login(client)
    client.cookies.set("aiorg_session", "garbage")
    assert client.get("/api/roles").status_code == 401


def test_seed_is_idempotent_and_versions_changes(client, tmp_path):
    from app.org.seed import seed_roles

    card = (
        'id: ceo\nname: CEO\ndepartment: executive\nreports_to: founder\nmodel: "X"\n'
        "provider: p\nsummary: s\nresponsibilities: []\n"
    )
    with Session(engine()) as s:
        assert seed_roles(s, "roles") == 0
        (tmp_path / "ceo.yaml").write_text(card)
        assert seed_roles(s, str(tmp_path)) == 1
        v = s.execute(text("select current_version from roles where slug='ceo'")).scalar()
        assert v == 2


def test_events_are_append_only(client):
    with Session(engine()) as s, pytest.raises(DBAPIError):
        s.execute(text("delete from events"))
    with Session(engine()) as s, pytest.raises(DBAPIError):
        s.execute(text("update events set kind='x'"))


def test_migration_down_and_up(db_url):
    alembic("downgrade", "base")
    alembic("upgrade", "head")


def test_ensure_founder_keeps_single_account(client, monkeypatch):
    from app.cli import ensure_founder

    monkeypatch.setenv("AIORG_FOUNDER_EMAIL", "new@x.io")
    monkeypatch.setenv("AIORG_FOUNDER_PASSWORD_HASH", "$argon2id$stub")
    ensure_founder()
    with Session(engine()) as s:
        emails = s.execute(text("select email from users")).scalars().all()
    assert emails == ["new@x.io"]


def test_session_dies_when_account_removed(client):
    login(client)
    assert client.get("/api/roles").status_code == 200
    with Session(engine()) as s:
        s.execute(text("delete from users"))
        s.commit()
    assert client.get("/api/roles").status_code == 401


def test_recreated_account_does_not_revive_session(client):
    from app.db.models import User

    login(client)
    with Session(engine()) as s:
        s.execute(text("delete from users"))
        s.add(User(email="f@x.io", password_hash="x"))  # noqa: S106
        s.commit()
    assert client.get("/api/roles").status_code == 401


def _csrf(client):
    return {"X-CSRF-Token": login(client).json()["csrf_token"]}


def test_tasks_require_auth_and_csrf(client):
    assert client.get("/api/tasks").status_code == 401
    assert client.get("/api/stream").status_code == 401
    h = _csrf(client)
    assert client.post("/api/tasks", json={"title": "x"}).status_code == 403
    assert client.post("/api/tasks", json={"title": "x"}, headers=h).status_code == 201


def test_task_validation(client):
    h = _csrf(client)
    assert client.post("/api/tasks", json={"title": ""}, headers=h).status_code == 422
    r = client.post("/api/tasks", json={"title": "t", "assignee": "nobody"}, headers=h)
    assert r.status_code == 422


def test_invalid_transition_rejected_and_audited(client):
    h = _csrf(client)
    tid = client.post("/api/tasks", json={"title": "t"}, headers=h).json()["id"]
    r = client.post(f"/api/tasks/{tid}/transition", json={"to": "completed"}, headers=h)
    assert r.status_code == 409
    assert client.get(f"/api/tasks/{tid}").json()["status"] == "ready"
    assert (
        client.post(f"/api/tasks/{tid}/transition", json={"to": "cancelled"}, headers=h).status_code
        == 200
    )
    assert (
        client.post(f"/api/tasks/{tid}/transition", json={"to": "ready"}, headers=h).status_code
        == 409
    )
    with Session(engine()) as s:
        n = s.execute(text("select count(*) from audit_log where task_id=:t"), {"t": tid}).scalar()
    assert n == 2


def test_echo_worker_completes_task_and_drives_role_status(client):
    from app.workers import echo

    h = _csrf(client)
    tid = client.post("/api/tasks", json={"title": "hello"}, headers=h).json()["id"]
    with Session(engine()) as s:
        task, run = echo.claim_one(s)
        assert task.status == "running"
        assert client.get("/api/roles/ceo").json()["status"] == "working"
        echo.finish(s, task, run)
    d = client.get(f"/api/tasks/{tid}").json()
    assert d["status"] == "completed" and d["check_record"]["passed"] is True
    kinds = [e["kind"] for e in d["events"]]
    assert kinds[0] == "task.created" and "run.output" in kinds and kinds[-1] == "role.status"
    assert client.get("/api/roles/ceo").json()["status"] == "idle"
    with Session(engine()) as s:
        assert echo.claim_one(s) is None


def test_restart_requeues_running_task(client):
    from app.workers import echo

    h = _csrf(client)
    tid = client.post("/api/tasks", json={"title": "x"}, headers=h).json()["id"]
    with Session(engine()) as s:
        echo.claim_one(s)
    with Session(engine()) as s:
        assert echo.reconcile(s) == 1
    d = client.get(f"/api/tasks/{tid}").json()
    assert d["status"] == "ready"
    assert client.get("/api/roles/ceo").json()["status"] == "idle"
    with Session(engine()) as s:
        run_status = s.execute(text("select status from runs")).scalar()
    assert run_status == "abandoned"


def test_stream_replays_missed_events(client):
    h = _csrf(client)
    client.post("/api/tasks", json={"title": "streamed"}, headers=h)
    evs = client.get("/api/events?limit=5").json()
    assert evs and evs[0]["seq"] < evs[-1]["seq"]
    first = evs[0]["seq"]
    with client.stream("GET", "/api/stream", headers={"Last-Event-ID": str(first - 1)}) as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        body = ""
        for chunk in r.iter_text():
            body += chunk
            if "task.created" in body:
                break
    assert f"id: {first}" in body and "task.created" in body
