"""Emergency stop, resume and the executor epoch. Lock order: control, task, run, role."""

from datetime import UTC, datetime

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core import tasks
from app.db.models import AuditLog, Run, Task, WorkerControl

ACTIVE = ("running", "verifying")


def get(db: Session, lock: str | None = None) -> WorkerControl:
    q = select(WorkerControl).where(WorkerControl.id == 1).execution_options(populate_existing=True)
    if lock:
        q = q.with_for_update(read=lock == "share")
    return db.scalars(q).one()


def set_idle_if_free(db: Session, slug: str, finished_task_id: str | None = None) -> None:
    """Mark a role idle only if it has no other running task. Locks the role row first, so two
    runs of one role finishing together cannot both see the other as still running."""
    from app.db.models import Role

    db.flush()
    db.execute(select(Role.id).where(Role.slug == slug).with_for_update())
    q = select(func.count()).select_from(Task).where(Task.assignee == slug, Task.status.in_(ACTIVE))
    if finished_task_id:
        q = q.where(Task.id != finished_task_id)
    if not db.scalar(q):
        tasks.set_role_status(db, slug, "idle", finished_task_id)


def cancel_active(db: Session, actor: str, reason: str) -> int:
    """Cancel every in-flight task. All task locks, then all run locks, then role writes.
    Caller commits."""
    active = list(
        db.scalars(select(Task).where(Task.status.in_(ACTIVE)).order_by(Task.id).with_for_update())
    )
    ids = [t.id for t in active]
    for run in db.scalars(
        select(Run)
        .where(Run.task_id.in_(ids), Run.status == "running")
        .order_by(Run.id)
        .with_for_update()
    ):
        run.status, run.finished_at = "cancelled", datetime.now(UTC)
    for task in active:
        tasks.transition(
            db,
            task,
            "cancelled",
            actor=actor,
            commit=False,
            reason=f"emergency stop: {reason}",
        )
    for slug in sorted({t.assignee for t in active}):
        set_idle_if_free(db, slug)
    return len(active)


def request_stop(db: Session, actor: str, reason: str) -> int:
    """Two commits. The first is the admission fence (nothing new can be claimed or spawned);
    the second cancels what was in flight. Startup recovery finishes the second if needed."""
    reason = reason.strip()[:160] or "requested by founder"
    db.rollback()
    db.execute(text("set local lock_timeout = '3s'"))
    control = get(db, "update")
    if not control.stopped:
        control.stopped, control.generation = True, control.generation + 1
        control.reason, control.actor = reason, actor
        control.requested_at = datetime.now(UTC)
        tasks.emit(db, "control.stopped", actor, payload={"reason": reason})
        db.add(AuditLog(actor=actor, action="control.stop", detail={"reason": reason}))
    generation = control.generation
    db.commit()
    return cancel_for_stop(db, generation, actor, reason)


def cancel_for_stop(db: Session, generation: int, actor: str, reason: str) -> int:
    """Second commit of a stop. Does nothing if that stop has since been resumed (resume cancels
    what was in flight itself, so work claimed afterwards must be left alone)."""
    db.execute(text("set local lock_timeout = '3s'"))
    control = get(db, "update")
    if not control.stopped or control.generation != generation:
        db.rollback()
        return 0
    n = cancel_active(db, actor, reason)
    db.commit()
    return n


def resume(db: Session, actor: str) -> None:
    """One transaction under the control lock, so no stop can slip in between its steps."""
    db.rollback()
    control = get(db, "update")
    if not control.stopped:
        db.rollback()
        return
    # finish a half-done stop before reopening admission
    cancel_active(db, actor, control.reason or "requested by founder")
    control.stopped, control.resumed_at = False, datetime.now(UTC)
    tasks.emit(db, "control.resumed", actor)
    db.add(AuditLog(actor=actor, action="control.resume", detail={}))
    db.commit()


def bump_epoch(db: Session) -> int:
    """Called by an executor right after it takes the executor lock; fences older ones."""
    control = get(db, "update")
    control.epoch += 1
    epoch = control.epoch
    db.commit()
    return epoch
