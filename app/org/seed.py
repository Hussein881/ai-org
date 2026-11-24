"""Seed roles from roles/*.yaml. Idempotent; a changed card creates a new version."""

from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Event, Role, RoleVersion


def seed_roles(db: Session, roles_dir: str) -> int:
    changed = 0
    for path in sorted(Path(roles_dir).glob("*.yaml")):
        card = yaml.safe_load(path.read_text())
        role = db.scalar(select(Role).where(Role.slug == card["id"]))
        if role is None:
            role = Role(
                slug=card["id"],
                name=card["name"],
                department=card["department"],
                reports_to=card["reports_to"],
            )
            db.add(role)
            db.flush()
            db.add(RoleVersion(role_id=role.id, version=1, card=card))
            db.add(Event(kind="role.seeded", actor="seed", payload={"slug": card["id"]}))
            changed += 1
            continue
        latest = db.scalar(
            select(RoleVersion)
            .where(RoleVersion.role_id == role.id)
            .order_by(RoleVersion.version.desc())
        )
        if latest is None or latest.card != card:
            ver = (latest.version if latest else 0) + 1
            db.add(RoleVersion(role_id=role.id, version=ver, card=card))
            role.current_version = ver
            role.name, role.department, role.reports_to = (
                card["name"],
                card["department"],
                card["reports_to"],
            )
            db.add(Event(kind="role.updated", actor="seed", payload={"slug": card["id"]}))
            changed += 1
    db.commit()
    return changed
