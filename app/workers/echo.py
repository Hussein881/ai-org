"""Fake in-process worker (no LLM): proves the task -> run -> events -> completed loop."""

import argparse
import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core import control, effects, tasks
from app.core.state import InvalidTransitionError
from app.db.models import Role, RoleVersion, Run, Task
from app.db.session import engine
from app.gateway.redact import redact_text
from app.gateway.router import Gateway, TaskRef
from app.gateway.types import (
    AllRoutesFailed,
    GatewayError,
    Halted,
    PromptPart,
    Queued,
    utcnow,
)
from app.workers import crash
from app.workers.lock import ExecutorLock

log = logging.getLogger("aiorg.echo")
ACTOR = "echo-worker"
CRASHED = {"abandoned_by": "restart"}  # marks a run that died with its executor
TRANSIENT_BACKOFF = (timedelta(seconds=10), timedelta(seconds=60))


def claim_one(
    db: Session, task_id: str | None = None, epoch: int | None = None
) -> tuple[Task, Run] | None:
    """Atomically take a ready task (the oldest, or `task_id`) and open a run.

    The shared lock on worker_control serializes this with an emergency stop: either the claim
    commits first and the stop cancels it, or the claim sees the stop. `epoch` fences an old
    executor; production entry points always pass it."""
    state_row = control.get(db, "share")
    if state_row.stopped or (epoch is not None and state_row.epoch != epoch):
        db.rollback()
        return None
    query = (
        select(Task)
        .where(Task.status == "ready")
        .where(or_(Task.retry_at.is_(None), Task.retry_at <= utcnow()))
        .order_by(Task.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if task_id is not None:
        query = query.where(Task.id == task_id)
    task = db.scalar(query)
    if task is None:
        db.rollback()
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
    """Give up a run we still own. A run that was cancelled or recovered is left alone."""
    if not _lock_owned(db, task, run):
        return
    run.status, run.finished_at = "abandoned", utcnow()
    tasks.emit(
        db, "run.abandoned", ACTOR, task_id=task.id, run_id=run.id, payload={"reason": reason}
    )
    control.set_idle_if_free(db, task.assignee, task.id)
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
    bind, run_id = db.get_bind(), run.id

    def run_cancelled() -> bool:
        # the process-wide halt reopens on resume; a run that a stop cancelled must stay quiet
        with Session(bind) as check:
            return check.scalar(select(Run.status).where(Run.id == run_id)) != "running"

    res = gateway.complete(
        task.assignee,
        TaskRef(task.id, run.id),
        parts,
        None,
        "founder_private",
        purpose="ack",
        max_output_tokens=60,
        cancelled=run_cancelled,
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


def _requeue(
    db: Session, task: Task, run: Run, resets_at: datetime, run_status: str = "abandoned"
) -> None:
    """Park this task until `resets_at`; other tasks keep flowing. Caller holds the ownership
    lock (anything else it added to the session commits with this)."""
    if task.status != "running":  # cancelled meanwhile: keep that decision
        _abandon(db, task, run, "task changed while running")
        return
    run.status, run.finished_at = run_status, utcnow()
    task.retry_at = resets_at
    db.flush()  # transition() re-reads the task row; unflushed changes would be lost
    tasks.emit(
        db,
        "gateway.queued",
        ACTOR,
        task_id=task.id,
        run_id=run.id,
        payload={"resets_at": resets_at.isoformat()},
    )
    tasks.transition(db, task, "ready", actor=ACTOR, commit=False)
    control.set_idle_if_free(db, task.assignee, task.id)
    db.commit()


def _fail(db: Session, task: Task, run: Run, reason: str) -> None:
    """Caller holds the ownership lock. failed_execution is the dead-letter list."""
    if task.status != "running":
        _abandon(db, task, run, "task changed while running")
        return
    run.status, run.finished_at = "failed", utcnow()
    tasks.emit(db, "run.failed", ACTOR, task_id=task.id, run_id=run.id, payload={"reason": reason})
    tasks.transition(db, task, "failed_execution", actor=ACTOR, commit=False, reason=reason)
    control.set_idle_if_free(db, task.assignee, task.id)
    db.commit()


def _retry_delay(db: Session, task: Task) -> timedelta | None:
    """Backoff for the next automatic retry, or None when the budget is spent."""
    used = db.scalar(
        select(func.count())
        .select_from(Run)
        .where(Run.task_id == task.id, Run.status == "transient")
    )
    if (used or 0) >= get_settings().transient_retries:
        return None
    return TRANSIENT_BACKOFF[min(used or 0, len(TRANSIENT_BACKOFF) - 1)]


def finish(db: Session, task: Task, run: Run, gateway: Gateway | None = None) -> None:
    """Reply (echo, or one real model call for the CEO), run the check, complete.
    Every outcome is written in one transaction under the ownership lock."""
    if not _lock_owned(db, task, run):
        return
    if task.status != "running":  # cancelled before dispatch: send nothing to any model
        _abandon(db, task, run, "task changed before the call")
        return
    output: dict[str, str] = {"echo": task.title}
    live = gateway is not None and task.assignee == "ceo"
    # looked up even with live replies off: a recovered task must not skip an unresolved call
    saved = effects.latest(db, task.id, effects.MODEL_ACK)
    effect_id: str | None = None
    if saved is not None and saved.status == "done" and saved.result:
        output, live = dict(saved.result), False  # replay: no second call
    elif saved is not None and saved.status in ("intent", "unknown"):
        # an earlier run may have reached the model and we cannot know: a human decides
        effects.resolve(db, saved.id, "unknown")
        _fail(db, task, run, "effect_unknown")
        return
    if live:
        crash.point("before_intent")
        effect_id = effects.begin(db, task.id, run.id, effects.MODEL_ACK).id
        db.commit()  # the intent is durable before anything is sent
    else:
        db.rollback()  # never hold row locks across a model call

    queued_until: datetime | None = None
    failure: str | None = None
    retryable = False
    halted: Halted | None = None
    if live and gateway is not None:
        try:
            output = {k: redact_text(v) for k, v in live_reply(db, task, run, gateway).items()}
        except Queued as q:
            queued_until = q.resets_at
        except Halted as h:
            halted = h
        except AllRoutesFailed as e:
            failure, retryable = type(e).__name__, e.retryable
        except GatewayError as e:
            failure = type(e).__name__
        if effect_id and not (queued_until or failure or halted):
            db.rollback()
            effects.resolve(db, effect_id, "done", output)  # saved on its own: replayable
            db.commit()
            crash.point("after_effect_done")

    if not _lock_owned(db, task, run):
        return
    if halted is not None:  # shutdown (an emergency stop has already cancelled the run)
        if effect_id:
            effects.resolve(db, effect_id, "unknown" if halted.sent else "failed")
        if halted.sent:
            _fail(db, task, run, "effect_unknown")
        else:
            _requeue(db, task, run, utcnow())
        return
    if queued_until is not None:
        if effect_id:
            effects.resolve(db, effect_id, "failed")
        _requeue(db, task, run, queued_until)
        return
    if failure is not None:
        if effect_id:
            effects.resolve(db, effect_id, "failed")
        delay = _retry_delay(db, task) if retryable else None
        if delay is not None:
            _requeue(db, task, run, utcnow() + delay, run_status="transient")
        else:
            _fail(db, task, run, failure)
        return
    output = {k: redact_text(v) for k, v in output.items()}
    try:
        tasks.emit(db, "run.output", ACTOR, task_id=task.id, run_id=run.id, payload=dict(output))
        tasks.transition(db, task, "verifying", actor=ACTOR, commit=False)
        passed = bool(next(iter(output.values())))
        check = {"kind": "deterministic", "check": "reply is non-empty", "passed": passed}
        run.status, run.result, run.finished_at = "succeeded", dict(output), utcnow()
        tasks.transition(
            db,
            task,
            "completed" if passed else "failed_qa",
            actor=ACTOR,
            check_record=check,
            commit=False,
        )
    except InvalidTransitionError:
        db.rollback()
        _abandon(db, task, run, "task changed while running")
        return
    tasks.emit(db, "run.finished", ACTOR, task_id=task.id, run_id=run.id)
    control.set_idle_if_free(db, task.assignee, task.id)
    db.commit()
    crash.point("after_complete")


def reconcile(db: Session) -> int:
    """Recovery. Only for the holder of the executor lock, before it runs anything: no other
    executor is alive, so every running task and run is abandoned work."""
    db.rollback()
    state_row = control.get(db)
    if state_row.stopped:  # finish an emergency stop that was interrupted
        control.cancel_active(db, ACTOR, state_row.reason or "requested by founder")
        db.commit()
    stuck = list(
        db.scalars(
            select(Task).where(Task.status.in_(control.ACTIVE)).order_by(Task.id).with_for_update()
        )
    )
    cap = get_settings().crash_retry_cap
    for task in stuck:
        for run in db.scalars(select(Run).where(Run.task_id == task.id, Run.status == "running")):
            run.status, run.finished_at, run.result = "abandoned", utcnow(), dict(CRASHED)
        db.flush()
        crashes = sum(
            r == CRASHED for r in db.scalars(select(Run.result).where(Run.task_id == task.id))
        )
        saved = effects.latest(db, task.id, effects.MODEL_ACK)
        limit = cap * 2 if saved is not None and saved.status == "done" else cap
        tasks.emit(db, "run.abandoned", ACTOR, task_id=task.id, payload={"reason": "restart"})
        if task.status == "running" and crashes >= limit:
            tasks.transition(
                db, task, "failed_execution", actor=ACTOR, commit=False, reason="crash_loop"
            )
        else:
            tasks.transition(db, task, "ready", actor=ACTOR, commit=False)
    # No worker survives a restart, so no run may stay `running` (e.g. a cancelled task's run).
    for run in db.scalars(select(Run).where(Run.status == "running")):
        run.status, run.finished_at = "abandoned", utcnow()
    db.flush()
    # A crash between completion and the idle reset can leave a role stuck on Working.
    for role in db.scalars(select(Role).where(Role.status == "working").order_by(Role.slug)):
        control.set_idle_if_free(db, role.slug)
    db.commit()
    return len(stuck)


async def loop() -> None:
    """In-process echo executor for development. Off in compose: the host worker is the executor.
    It does nothing unless it holds the executor lock, so it can never compete with the host."""
    settings = get_settings()
    delay = settings.echo_seconds
    gateway: Gateway | None = None
    if settings.ceo_live_reply:
        from app.gateway.factory import build_gateway

        gateway = build_gateway()
    lock = ExecutorLock(engine())
    try:
        while True:
            try:
                if not lock.alive():
                    lock.release()
                    if not lock.acquire():
                        await asyncio.sleep(2)
                        continue
                    with Session(engine()) as db:
                        epoch = control.bump_epoch(db)
                        reconcile(db)
                with Session(engine()) as db:
                    claimed = claim_one(db, epoch=epoch)
                    if claimed is None:
                        await asyncio.sleep(1)
                        continue
                    await asyncio.sleep(delay)
                    await asyncio.to_thread(finish, db, *claimed, gateway)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("echo worker step failed")
                lock.release()  # recover whatever this step left behind
                await asyncio.sleep(2)
    finally:
        lock.release()


def main() -> None:
    """Host launcher: `--once` claims one ready task, replies via the live gateway, exits."""
    from app.gateway.factory import build_gateway
    from app.gateway.redact import install_log_redaction

    install_log_redaction()
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", required=True)
    ap.parse_args()
    lock = ExecutorLock(engine())
    if not lock.acquire():
        print("another worker is running; stop aiorg-worker.service first")
        return
    try:
        with Session(engine()) as db:
            epoch = control.bump_epoch(db)
            reconcile(db)
            claimed = claim_one(db, epoch=epoch)
            if claimed is None:
                print("no ready task")
                return
            task, run = claimed
            finish(db, task, run, build_gateway())
            db.refresh(task)
            print(f"task {task.id} -> {task.status}")
    finally:
        lock.release()


if __name__ == "__main__":
    main()
