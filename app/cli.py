"""python -m app.cli hash-password | create-founder"""

import getpass
import sys
from pathlib import Path

from argon2 import PasswordHasher
from sqlalchemy import delete, select
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
        # Single founder account: drop any account left over from a previous email.
        db.execute(delete(User).where(User.email != s.founder_email))
        db.commit()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "hash-password":
        print(PasswordHasher().hash(getpass.getpass("Founder password: ")))
    elif cmd == "set-password":
        # Run in a real terminal (SSH). Writes the hash into .env; then `docker compose up -d`.
        pw = getpass.getpass("New founder password: ")
        if len(pw) < 12 or pw != getpass.getpass("Repeat: "):
            sys.exit("Passwords differ or are shorter than 12 characters; nothing changed.")
        env = Path(".env")
        lines = [
            x
            for x in env.read_text().splitlines()
            if not x.startswith("AIORG_FOUNDER_PASSWORD_HASH=")
        ]
        lines.append(f"AIORG_FOUNDER_PASSWORD_HASH='{PasswordHasher().hash(pw)}'")
        env.write_text("\n".join(lines) + "\n")
        print("Saved to .env. Now run: docker compose up -d")
    elif cmd == "ensure-founder":
        ensure_founder()
    else:
        sys.exit("usage: python -m app.cli hash-password|set-password|ensure-founder")
