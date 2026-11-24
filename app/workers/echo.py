"""Fake in-process worker (no LLM): proves the task -> run -> events -> completed loop."""

import asyncio
import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core import tasks
from app.core.state import InvalidTransitionError
from app.db.models import Role, Run, Task
from app.db.session import engine

log = logging.getLogger("aiorg.echo")
ACTOR = "echo-worker"


def claim_one(db: Session) -> tuple[Task, Run] | None:
    """Atomically take the oldest ready task (FOR UPDATE SKIP LOCKED) and open a run."""
    task = db.scalar(
        select(Task)
        .where(Task.status == "ready")
        .order_by(Task.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if task is None:
        return None
    attempt = (
        db.scalar(select(func.count()).select_from(Run).where(Run.task_id == task.id)) or 0
    ) + 1
    run = Run(task_id=task.id, attempt=attempt)
    db.add(run)
    db.flush()
    tasks.emit(
        db, "run.started", ACTOR, task_id=task.id, run_id=run.id, payload={"attempt": attempt}
    )
    tasks.set_role_status(db, task.assignee, "working", task.id)
    tasks.transition(db, task, "running", actor=ACTOR)
    return task, run


def _abandon(db: Session, task: Task, run: Run, reason: str) -> None:
    db.rollback()
    run.status = "abandoned"
    tasks.emit(
        db, "run.abandoned", ACTOR, task_id=task.id, run_id=run.id, payload={"reason": reason}
    )
    tasks.set_role_status(db, task.assignee, "idle", task.id)
    db.commit()


def finish(db: Session, task: Task, run: Run) -> None:
    """Echo the task back, run the deterministic check, and complete (unless it was cancelled)."""
    try:
        tasks.emit(
            db, "run.output", ACTOR, task_id=task.id, run_id=run.id, payload={"echo": task.title}
        )
        tasks.transition(db, task, "verifying", actor=ACTOR)
        check = {"kind": "deterministic", "check": "echo matches title", "passed": task.title != ""}
        run.status, run.result = "succeeded", {"echo": task.title}
        tasks.transition(
            db,
            task,
            "completed" if check["passed"] else "failed_qa",
            actor=ACTOR,
            check_record=check,
        )
    except InvalidTransitionError:
        _abandon(db, task, run, "task changed while running")
        return
    tasks.emit(db, "run.finished", ACTOR, task_id=task.id, run_id=run.id)
    tasks.set_role_status(db, task.assignee, "idle", task.id)
    db.commit()


def reconcile(db: Session) -> int:
    """After a restart, a running/verifying task has no live worker: abandon its run, requeue."""
    stuck = db.scalars(select(Task).where(Task.status.in_(("running", "verifying")))).all()
    for task in stuck:
        for run in db.scalars(select(Run).where(Run.task_id == task.id, Run.status == "running")):
            run.status = "abandoned"
        tasks.emit(db, "run.abandoned", ACTOR, task_id=task.id, payload={"reason": "restart"})
        tasks.set_role_status(db, task.assignee, "idle", task.id)
        tasks.transition(db, task, "ready", actor=ACTOR)
    # No worker survives a restart, so no run may stay `running` (e.g. a cancelled task's run).
    for run in db.scalars(select(Run).where(Run.status == "running")):
        run.status = "abandoned"
    # A crash between completion and the idle reset can leave a role stuck on Working.
    busy = {t.assignee for t in db.scalars(select(Task).where(Task.status == "running"))}
    for role in db.scalars(select(Role).where(Role.status == "working")):
        if role.slug not in busy:
            tasks.set_role_status(db, role.slug, "idle")
    db.commit()
    return len(stuck)


async def loop() -> None:
    delay = get_settings().echo_seconds
    with Session(engine()) as db:
        reconcile(db)
    while True:
        try:
            with Session(engine()) as db:
                claimed = claim_one(db)
                if claimed is None:
                    await asyncio.sleep(1)
                    continue
                await asyncio.sleep(delay)
                finish(db, *claimed)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("echo worker step failed")
            await asyncio.sleep(2)
