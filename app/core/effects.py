"""external_effect: written before a side effect starts and after it ends.

intent -> done (result saved) | failed (safe to try again) | unknown (may have happened).
An `intent` left behind by a dead run is never re-executed without the founder's retry.
"""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import tasks
from app.db.models import AuditLog, ExternalEffect, Task

MODEL_ACK = "model_ack"


def latest(db: Session, task_id: str, kind: str) -> ExternalEffect | None:
    return db.scalars(
        select(ExternalEffect)
        .where(ExternalEffect.task_id == task_id, ExternalEffect.kind == kind)
        .order_by(ExternalEffect.attempt.desc())
        .limit(1)
        .execution_options(populate_existing=True)
    ).first()


def begin(db: Session, task_id: str, run_id: str, kind: str) -> ExternalEffect:
    """Caller holds the run's ownership lock and commits before performing the effect."""
    prev = latest(db, task_id, kind)
    n = prev.attempt + 1 if prev else 1
    row = ExternalEffect(
        task_id=task_id,
        run_id=run_id,
        kind=kind,
        attempt=n,
        idempotency_key=f"{task_id}:{kind}#{n}",
        status="intent",
        data_class="founder_private",
    )
    db.add(row)
    db.flush()
    return row


def resolve(db: Session, effect_id: str, status: str, result: dict[str, str] | None = None) -> None:
    """Caller commits."""
    row = db.get(ExternalEffect, effect_id, with_for_update=True, populate_existing=True)
    if row is None or row.status in ("done", "superseded"):
        return
    row.status, row.updated_at = status, datetime.now(UTC)
    if result is not None:
        row.result = dict(result)


def last_retry_at(db: Session, task_id: str) -> datetime | None:
    """When the founder last retried this task: automatic retry and crash budgets restart there."""
    return db.scalar(
        select(func.max(AuditLog.created_at)).where(
            AuditLog.task_id == task_id, AuditLog.action == "task.retry"
        )
    )


def founder_retry(db: Session, task: Task, actor: str) -> None:
    """The one audited way a failed task runs again. Supersedes effects with unknown outcome, which
    allows one new model call. A saved (`done`) reply is kept and reused. Commits."""
    db.refresh(task, with_for_update=True)
    superseded = []
    for row in db.scalars(
        select(ExternalEffect).where(
            ExternalEffect.task_id == task.id, ExternalEffect.status.in_(("intent", "unknown"))
        )
    ):
        row.status, row.updated_at = "superseded", datetime.now(UTC)
        superseded.append(row.idempotency_key)
    db.add(
        AuditLog(
            actor=actor, action="task.retry", task_id=task.id, detail={"superseded": superseded}
        )
    )
    task.retry_at = None
    db.flush()  # transition() re-reads the task row
    tasks.transition(db, task, "ready", actor=actor)
