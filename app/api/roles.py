from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import current_session
from app.db.models import Role, RoleVersion
from app.db.session import get_db

router = APIRouter(prefix="/api/roles", tags=["roles"], dependencies=[Depends(current_session)])


class RoleOut(BaseModel):
    slug: str
    name: str
    department: str
    reports_to: str
    model: str
    provider: str
    status: str
    version: int


class RoleDetail(RoleOut):
    summary: str
    responsibilities: list[str]


def _card(db: Session, role: Role) -> dict[str, Any]:
    rv = db.scalar(
        select(RoleVersion).where(
            RoleVersion.role_id == role.id, RoleVersion.version == role.current_version
        )
    )
    return rv.card if rv else {}


def _out(db: Session, role: Role) -> RoleOut:
    card = _card(db, role)
    return RoleOut(
        slug=role.slug,
        name=role.name,
        department=role.department,
        reports_to=role.reports_to,
        model=card.get("model", ""),
        provider=card.get("provider", ""),
        status=role.status,
        version=role.current_version,
    )


@router.get("", response_model=list[RoleOut])
def list_roles(db: Session = Depends(get_db)) -> list[RoleOut]:
    return [_out(db, r) for r in db.scalars(select(Role).order_by(Role.created_at, Role.slug))]


@router.get("/{slug}", response_model=RoleDetail)
def get_role(slug: str, db: Session = Depends(get_db)) -> RoleDetail:
    role = db.scalar(select(Role).where(Role.slug == slug))
    if role is None:
        raise HTTPException(404, "Role not found")
    card = _card(db, role)
    return RoleDetail(
        **_out(db, role).model_dump(),
        summary=card.get("summary", ""),
        responsibilities=card.get("responsibilities", []),
    )
