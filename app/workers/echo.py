"""Fake in-process worker (no LLM): proves the task -> run -> events -> completed loop."""

import argparse
import asyncio
import logging
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core import tasks
from app.core.state import InvalidTransitionError
from app.db.models import Role, RoleVersion, Run, Task
from app.db.session import engine
from app.gateway.redact import redact_text
from app.gateway.router import Gateway, TaskRef
from app.gateway.types import GatewayError, PromptPart, Queued, utcnow

log = logging.getLogger("aiorg.echo")
ACTOR = "echo-worker"


def claim_one(db: Session) -> tuple[Task, Run] | None:
    """Atomically take the oldest ready task (FOR UPDATE SKIP LOCKED) and open a run."""
    task = db.scalar(
        select(Task)
        .where(Task.status == "ready")
        .where(or_(Task.retry_at.is_(None), Task.retry_at <= utcnow()))
        .order_by(Task.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if task is None:
        return None
    task.retry_at = None
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


def _card_text(db: Session, slug: str) -> str:
    role = db.scalar(select(Role).where(Role.slug == slug))
    rv = db.scalar(
        select(RoleVersion).where(
            RoleVersion.role_id == (role.id if role else ""),
            RoleVersion.version == (role.current_version if role else 0),
        )
    )
    card = rv.card if rv else {}
    return f"You are the {card.get('name', slug)}. {card.get('summary', '')}"


def live_reply(db: Session, task: Task, run: Run, gateway: Gateway) -> dict[str, str]:
    """One model call: a one-line acknowledgement. Malformed output never triggers a second call."""
    parts = [
        PromptPart("role_card", _card_text(db, task.assignee), "public"),
        PromptPart(
            "task",
            f"Task title: {task.title}\nDetails: {task.description}\n"
            "Acknowledge this task from the founder in one short sentence.",
            "founder_private",
            untrusted=True,
        ),
    ]
    res = gateway.complete(
        task.assignee,
        TaskRef(task.id, run.id),
        parts,
        None,
        "founder_private",
        purpose="ack",
        max_output_tokens=60,
    )
    line = next((x.strip() for x in res.text.splitlines() if x.strip()), "")[:300]
    if not line:
        return {
            "reply": f"Received: {task.title}",
            "provider": res.provider,
            "model": res.model,
            "source": "fallback",
        }
    return {"reply": line, "provider": res.provider, "model": res.model, "source": "model"}


def _lock_owned(db: Session, task: Task, run: Run) -> bool:
    """Lock task then run. True if this attempt still owns the run; the locks are held until
    the caller commits, so reconciliation cannot take the run away between check and write."""
    db.rollback()
    db.refresh(task, with_for_update=True)
    db.refresh(run, with_for_update=True)
    if run.status != "running":
        db.rollback()
        return False
    return True


def _requeue(db: Session, task: Task, run: Run, resets_at: datetime) -> None:
    """Quota/rate limit: park this task until the reset; other tasks keep flowing.
    Caller holds the ownership lock."""
    if task.status != "running":  # cancelled meanwhile: keep that decision
        _abandon(db, task, run, "task changed while running")
        return
    run.status = "abandoned"
    task.retry_at = resets_at
    tasks.emit(
        db,
        "gateway.queued",
        ACTOR,
        task_id=task.id,
        run_id=run.id,
        payload={"resets_at": resets_at.isoformat()},
    )
    tasks.set_role_status(db, task.assignee, "idle", task.id)
    db.flush()
    tasks.transition(db, task, "ready", actor=ACTOR)


def _fail(db: Session, task: Task, run: Run, reason: str) -> None:
    """Caller holds the ownership lock."""
    if task.status != "running":
        _abandon(db, task, run, "task changed while running")
        return
    run.status = "failed"
    tasks.emit(db, "run.failed", ACTOR, task_id=task.id, run_id=run.id, payload={"reason": reason})
    tasks.set_role_status(db, task.assignee, "idle", task.id)
    db.flush()
    tasks.transition(db, task, "failed_execution", actor=ACTOR)


def finish(db: Session, task: Task, run: Run, gateway: Gateway | None = None) -> None:
    """Reply (echo, or one real model call for the CEO), run the check, complete.
    Every outcome is written in one transaction under the ownership lock."""
    if not _lock_owned(db, task, run):
        return
    if task.status != "running":  # cancelled before dispatch: send nothing to any model
        _abandon(db, task, run, "task changed before the call")
        return
    db.rollback()  # never hold row locks across a model call
    output: dict[str, str] = {"echo": task.title}
    queued_until: datetime | None = None
    failure: str | None = None
    if gateway is not None and task.assignee == "ceo":
        try:
            output = live_reply(db, task, run, gateway)
        except Queued as q:
            queued_until = q.resets_at
        except GatewayError as e:
            failure = type(e).__name__
    if not _lock_owned(db, task, run):
        return
    if queued_until is not None:
        _requeue(db, task, run, queued_until)
        return
    if failure is not None:
        _fail(db, task, run, failure)
        return
    output = {k: redact_text(v) for k, v in output.items()}
    try:
        tasks.emit(db, "run.output", ACTOR, task_id=task.id, run_id=run.id, payload=dict(output))
        tasks.transition(db, task, "verifying", actor=ACTOR, commit=False)
        passed = bool(next(iter(output.values())))
        check = {"kind": "deterministic", "check": "reply is non-empty", "passed": passed}
        run.status, run.result = "succeeded", dict(output)
        tasks.transition(
            db,
            task,
            "completed" if passed else "failed_qa",
            actor=ACTOR,
            check_record=check,
            commit=False,
        )
    except InvalidTransitionError:
        _abandon(db, task, run, "task changed while running")
        return
    tasks.emit(db, "run.finished", ACTOR, task_id=task.id, run_id=run.id)
    tasks.set_role_status(db, task.assignee, "idle", task.id)
    db.commit()


def reconcile(db: Session) -> int:
    """After a restart, a running/verifying task has no live worker: abandon its run, requeue."""
    stuck = db.scalars(
        select(Task)
        .where(Task.status.in_(("running", "verifying")))
        .with_for_update(skip_locked=True)
    ).all()
    for task in stuck:
        for run in db.scalars(select(Run).where(Run.task_id == task.id, Run.status == "running")):
            run.status = "abandoned"
        tasks.emit(db, "run.abandoned", ACTOR, task_id=task.id, payload={"reason": "restart"})
        tasks.set_role_status(db, task.assignee, "idle", task.id)
        tasks.transition(db, task, "ready", actor=ACTOR, commit=False)
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
    settings = get_settings()
    delay = settings.echo_seconds
    gateway: Gateway | None = None
    if settings.ceo_live_reply:
        from app.gateway.factory import build_gateway

        gateway = build_gateway()
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
                await asyncio.to_thread(finish, db, *claimed, gateway)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("echo worker step failed")
            await asyncio.sleep(2)


def main() -> None:
    """Host launcher: `--once` claims one ready task, replies via the live gateway, exits."""
    from app.gateway.factory import build_gateway
    from app.gateway.redact import install_log_redaction

    install_log_redaction()
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", required=True)
    ap.parse_args()
    with Session(engine()) as db:
        claimed = claim_one(db)
        if claimed is None:
            print("no ready task")
            return
        task, run = claimed
        finish(db, task, run, build_gateway())
        db.refresh(task)
        print(f"task {task.id} -> {task.status}")


if __name__ == "__main__":
    main()
