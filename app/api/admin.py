"""Founder controls: worker health, emergency stop / resume, dead-letter list. CSRF on writes."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api.auth import current_session
from app.core import control, effects
from app.db.models import Run, Task, WorkerStatus
from app.db.session import get_db
from app.gateway.types import utcnow

HEARTBEAT_FRESH = timedelta(seconds=10)

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(current_session)])


class AdminStatus(BaseModel):
    worker_alive: bool
    heartbeat_at: datetime | None
    in_flight: int
    stopped: bool
    stop_reason: str | None
    dead_letter_count: int


class StopIn(BaseModel):
    reason: str = Field(default="", max_length=160)


class DeadLetter(BaseModel):
    id: str
    title: str
    assignee: str
    reason: str | None
    attempts: int
    updated_at: datetime


def _status(db: Session) -> AdminStatus:
    state = control.get(db)
    worker = db.get(WorkerStatus, 1, populate_existing=True)
    beat = worker.heartbeat_at if worker else None
    alive = beat is not None and utcnow() - beat < HEARTBEAT_FRESH
    dead = db.scalar(
        select(func.count()).select_from(Task).where(Task.status == "failed_execution")
    )
    return AdminStatus(
        worker_alive=alive,
        heartbeat_at=beat,
        in_flight=worker.in_flight if worker and alive else 0,
        stopped=state.stopped,
        stop_reason=state.reason if state.stopped else None,
        dead_letter_count=dead or 0,
    )


@router.get("/status", response_model=AdminStatus)
def status(db: Session = Depends(get_db)) -> AdminStatus:
    return _status(db)


@router.post("/stop", response_model=AdminStatus)
def stop(
    body: StopIn, session: dict[str, str] = Depends(current_session), db: Session = Depends(get_db)
) -> AdminStatus:
    try:
        control.request_stop(db, session["email"], body.reason)
    except OperationalError:
        db.rollback()
        if not control.get(db).stopped:
            raise HTTPException(
                503, "Could not stop yet, the database is busy. Try again."
            ) from None
        # the admission fence is committed; the worker finishes the cancellation
    return _status(db)


@router.post("/resume", response_model=AdminStatus)
def resume(
    session: dict[str, str] = Depends(current_session), db: Session = Depends(get_db)
) -> AdminStatus:
    control.resume(db, session["email"])
    return _status(db)


@router.get("/dead-letter", response_model=list[DeadLetter])
def dead_letter(db: Session = Depends(get_db)) -> list[DeadLetter]:
    rows = db.execute(
        select(Task, func.count(Run.id))
        .outerjoin(Run, Run.task_id == Task.id)
        .where(Task.status == "failed_execution")
        .group_by(Task.id)
        .order_by(Task.updated_at.desc())
        .limit(200)
    ).all()
    return [
        DeadLetter(
            id=t.id,
            title=t.title,
            assignee=t.assignee,
            reason=t.status_reason,
            attempts=n,
            updated_at=t.updated_at,
        )
        for t, n in rows
    ]


@router.post("/dead-letter/{task_id}/retry", status_code=204)
def retry(
    task_id: str,
    session: dict[str, str] = Depends(current_session),
    db: Session = Depends(get_db),
) -> None:
    task = db.get(Task, task_id, with_for_update=True)
    if task is None:
        raise HTTPException(404, "Task not found")
    if task.status != "failed_execution":
        raise HTTPException(409, "Only failed tasks can be retried")
    effects.founder_retry(db, task, session["email"])
