"""Task service: every state change is one transaction that also writes event + audit rows."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import state
from app.db.models import AuditLog, Event, Role, Task


def emit(
    db: Session,
    kind: str,
    actor: str,
    *,
    task_id: str | None = None,
    run_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    db.add(Event(kind=kind, actor=actor, task_id=task_id, run_id=run_id, payload=payload or {}))


def set_role_status(db: Session, slug: str, status: str, task_id: str | None = None) -> None:
    role = db.scalar(select(Role).where(Role.slug == slug))
    if role is not None and role.status != status:
        role.status = status
        emit(db, "role.status", slug, task_id=task_id, payload={"slug": slug, "status": status})


def create_task(db: Session, *, title: str, description: str, assignee: str, actor: str) -> Task:
    if db.scalar(select(Role.id).where(Role.slug == assignee)) is None:
        raise LookupError(f"unknown role: {assignee}")
    task = Task(
        title=title, description=description, assignee=assignee, actor=actor, status="ready"
    )
    db.add(task)
    db.flush()
    emit(db, "task.created", actor, task_id=task.id, payload={"title": title, "assignee": assignee})
    # Edge animation in the UI: a message passes from the founder to the assignee.
    emit(db, "message", actor, task_id=task.id, payload={"from": "founder", "to": assignee})
    db.add(AuditLog(actor=actor, action="task.create", task_id=task.id, detail={"to": "ready"}))
    db.commit()
    return task


def transition(
    db: Session,
    task: Task,
    target: str,
    *,
    actor: str,
    check_record: dict[str, Any] | None = None,
) -> Task:
    """Validated move. Raises InvalidTransitionError; caller commits via this function."""
    if check_record is not None:
        task.check_record = check_record
    new = state.check(task.status, target, has_check_record=task.check_record is not None)
    old = task.status
    task.status = new.value
    task.updated_at = datetime.now(UTC)
    emit(db, "task.status", actor, task_id=task.id, payload={"from": old, "to": new.value})
    db.add(
        AuditLog(
            actor=actor,
            action="task.transition",
            task_id=task.id,
            detail={"from": old, "to": new.value},
        )
    )
    db.commit()
    return task
