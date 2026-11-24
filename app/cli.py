"""python -m app.cli hash-password | create-founder"""

import getpass
import sys

from argon2 import PasswordHasher
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import User
from app.db.session import engine


def ensure_founder() -> None:
    """Create/refresh the single founder account from AIORG_FOUNDER_* env (hash only)."""
    s = get_settings()
    if not s.founder_password_hash:
        print("AIORG_FOUNDER_PASSWORD_HASH not set; skipping founder creation")
        return
    with Session(engine()) as db:
        user = db.scalar(select(User).where(User.email == s.founder_email))
        if user is None:
            db.add(User(email=s.founder_email, password_hash=s.founder_password_hash))
        else:
            user.password_hash = s.founder_password_hash
        db.commit()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "hash-password":
        print(PasswordHasher().hash(getpass.getpass("Founder password: ")))
    elif cmd == "ensure-founder":
        ensure_founder()
    else:
        sys.exit("usage: python -m app.cli hash-password|ensure-founder")
