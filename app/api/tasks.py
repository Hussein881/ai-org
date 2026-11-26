import asyncio
import json
import time
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import current_session
from app.core import effects, state, tasks
from app.db.models import Event, Task
from app.db.session import engine, get_db

STREAM_MAX_SECONDS = 600

router = APIRouter(prefix="/api", tags=["tasks"], dependencies=[Depends(current_session)])


class TaskIn(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    description: str = Field(default="", max_length=5000)
    assignee: str = "ceo"


class TaskOut(BaseModel):
    id: str
    title: str
    description: str
    status: str
    assignee: str
    created_at: datetime
    updated_at: datetime
    status_reason: str | None = None


class EventOut(BaseModel):
    seq: int
    kind: str
    actor: str
    task_id: str | None
    payload: dict[str, Any]
    created_at: datetime


class TaskDetail(TaskOut):
    check_record: dict[str, Any] | None
    events: list[EventOut]


FOUNDER_TARGETS = {"cancelled", "ready"}  # running/verifying/completed belong to workers


class TransitionIn(BaseModel):
    to: str


def _task_out(t: Task) -> TaskOut:
    return TaskOut.model_validate(t, from_attributes=True)


def _event_out(e: Event) -> EventOut:
    return EventOut.model_validate(e, from_attributes=True)


@router.post("/tasks", response_model=TaskOut, status_code=201)
def create_task(
    body: TaskIn, session: dict[str, str] = Depends(current_session), db: Session = Depends(get_db)
) -> TaskOut:
    try:
        task = tasks.create_task(
            db,
            title=body.title,
            description=body.description,
            assignee=body.assignee,
            actor=session["email"],
        )
    except LookupError as e:
        raise HTTPException(422, str(e)) from None
    return _task_out(task)


@router.get("/tasks", response_model=list[TaskOut])
def list_tasks(db: Session = Depends(get_db)) -> list[TaskOut]:
    rows = db.scalars(select(Task).order_by(Task.created_at.desc()).limit(200))
    return [_task_out(t) for t in rows]


@router.get("/tasks/{task_id}", response_model=TaskDetail)
def get_task(task_id: str, db: Session = Depends(get_db)) -> TaskDetail:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "Task not found")
    events = db.scalars(select(Event).where(Event.task_id == task_id).order_by(Event.seq))
    return TaskDetail(
        **_task_out(task).model_dump(),
        check_record=task.check_record,
        events=[_event_out(e) for e in events],
    )


@router.post("/tasks/{task_id}/transition", response_model=TaskOut)
def transition_task(
    task_id: str,
    body: TransitionIn,
    session: dict[str, str] = Depends(current_session),
    db: Session = Depends(get_db),
) -> TaskOut:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "Task not found")
    db.refresh(task, with_for_update=True)  # decide on the locked, current status
    if body.to not in FOUNDER_TARGETS or (
        body.to == "ready" and task.status in ("running", "verifying")
    ):
        raise HTTPException(409, f"a task cannot be moved to {body.to} from the dashboard")
    try:
        if task.status == "failed_execution" and body.to == "ready":
            effects.founder_retry(db, task, session["email"])
        else:
            tasks.transition(db, task, body.to, actor=session["email"])
    except state.InvalidTransitionError as e:
        db.rollback()
        raise HTTPException(409, str(e)) from None
    return _task_out(task)


@router.get("/events", response_model=list[EventOut])
def recent_events(limit: int = 30, db: Session = Depends(get_db)) -> list[EventOut]:
    rows = db.scalars(select(Event).order_by(Event.seq.desc()).limit(min(max(limit, 1), 200)))
    return [_event_out(e) for e in reversed(rows.all())]


REREAD_WINDOW = 200  # sequence numbers can commit out of order; re-read recent ones and dedupe


def _fetch_after(seq: int) -> list[EventOut]:
    with Session(engine()) as db:
        rows = db.scalars(
            select(Event).where(Event.seq > seq - REREAD_WINDOW).order_by(Event.seq).limit(400)
        )
        return [_event_out(e) for e in rows]


def _latest_seq() -> int:
    with Session(engine()) as db:
        last = db.scalar(select(Event.seq).order_by(Event.seq.desc()).limit(1))
        return last or 0


@router.get("/stream")
async def stream(request: Request) -> StreamingResponse:
    """Server-sent events. Reconnecting clients send Last-Event-ID and get what they missed."""
    header = request.headers.get("last-event-id")
    start = int(header) if header and header.isdigit() else await asyncio.to_thread(_latest_seq)

    async def gen() -> AsyncIterator[str]:
        last = start
        seen: set[int] = set()
        deadline = time.monotonic() + STREAM_MAX_SECONDS  # forces periodic re-authentication
        yield f"retry: 2000\nid: {start}\n\n"  # so a reconnect always resumes from here
        while time.monotonic() < deadline and not await request.is_disconnected():
            events = await asyncio.to_thread(_fetch_after, last)
            fresh = [e for e in events if e.seq > start and e.seq not in seen]
            for e in fresh:
                seen.add(e.seq)
                last = max(last, e.seq)
                data = json.dumps(e.model_dump(mode="json"))
                yield f"id: {e.seq}\nevent: aiorg\ndata: {data}\n\n"
            seen = {x for x in seen if x > last - REREAD_WINDOW}
            if not fresh:
                yield ": keepalive\n\n"
            await asyncio.sleep(0.7)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
