"""Single-founder login: argon2 hash, signed session cookie, CSRF header on mutations."""

import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import Event, User
from app.db.session import get_db

COOKIE = "aiorg_session"
_hasher = PasswordHasher()
# Verified against when the account is unknown, so timing doesn't reveal it.
_DUMMY = _hasher.hash("not-a-real-password")

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str
    password: str


class SessionOut(BaseModel):
    email: str
    csrf_token: str


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    if len(settings.session_secret) < 32:
        raise RuntimeError("AIORG_SESSION_SECRET must be at least 32 characters")
    return URLSafeTimedSerializer(settings.session_secret, salt="aiorg-session")


def current_session(
    request: Request,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    raw = request.cookies.get(COOKIE)
    if not raw:
        raise HTTPException(401, "Not authenticated")
    try:
        data = _serializer(settings).loads(raw, max_age=settings.session_max_age)
    except BadSignature:
        raise HTTPException(401, "Not authenticated") from None
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        sent = request.headers.get("x-csrf-token", "")
        if not hmac.compare_digest(sent, data["csrf"]):
            raise HTTPException(403, "CSRF token missing or invalid")
    # The account must still exist: removing/replacing the founder ends old sessions.
    if db.scalar(select(User.id).where(User.email == data["email"])) is None:
        raise HTTPException(401, "Not authenticated")
    return {"email": data["email"], "csrf": data["csrf"]}


@router.post("/login", response_model=SessionOut)
def login(
    body: LoginIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SessionOut:
    # Browsers cannot add this header cross-origin without a preflight (login CSRF guard).
    if request.headers.get("x-requested-with") != "aiorg":
        raise HTTPException(403, "Missing X-Requested-With header")
    user = db.scalar(select(User).where(User.email == body.email))
    try:
        _hasher.verify(user.password_hash if user else _DUMMY, body.password)
        ok = user is not None
    except VerifyMismatchError:
        ok = False
    if not ok or user is None:
        db.add(Event(kind="auth.login_failed", actor="anonymous", payload={}))
        db.commit()
        raise HTTPException(401, "Invalid email or password")
    csrf = secrets.token_urlsafe(32)
    token = _serializer(settings).dumps({"email": user.email, "csrf": csrf})
    response.set_cookie(
        COOKIE,
        token,
        max_age=settings.session_max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )
    db.add(Event(kind="auth.login", actor=user.email, payload={}))
    db.commit()
    return SessionOut(email=user.email, csrf_token=csrf)


@router.get("/me", response_model=SessionOut)
def me(session: dict[str, str] = Depends(current_session)) -> SessionOut:
    return SessionOut(email=session["email"], csrf_token=session["csrf"])


@router.post("/logout", status_code=204)
def logout(response: Response, _: dict[str, str] = Depends(current_session)) -> None:
    response.delete_cookie(COOKIE, path="/")
