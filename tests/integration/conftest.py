import os
import subprocess
import sys

import pytest
from argon2 import PasswordHasher
from sqlalchemy import create_engine, text

URL = os.environ.get("AIORG_TEST_DATABASE_URL")


def alembic(*args: str) -> None:
    env = {**os.environ, "AIORG_DATABASE_URL": URL or "", "AIORG_SESSION_SECRET": "x" * 40}
    subprocess.run([sys.executable, "-m", "alembic", *args], check=True, env=env)


@pytest.fixture
def db_url(monkeypatch):
    if not URL:
        pytest.skip("AIORG_TEST_DATABASE_URL not set")
    eng = create_engine(URL)
    with eng.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    alembic("upgrade", "head")
    monkeypatch.setenv("AIORG_DATABASE_URL", URL)
    monkeypatch.setenv("AIORG_SESSION_SECRET", "s" * 40)
    monkeypatch.setenv("AIORG_COOKIE_SECURE", "false")
    monkeypatch.setenv("AIORG_ROLES_DIR", "roles")
    from app.db import session

    session.engine.cache_clear()
    yield URL
    session.engine.cache_clear()
    eng.dispose()


@pytest.fixture
def client(db_url):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from app.api.main import app
    from app.db.models import User
    from app.db.session import engine

    with Session(engine()) as s:
        s.add(User(email="f@x.io", password_hash=PasswordHasher().hash("pw-correct")))
        s.commit()
    with TestClient(app) as c:
        yield c
