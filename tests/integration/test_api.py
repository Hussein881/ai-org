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
