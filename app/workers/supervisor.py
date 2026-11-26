"""What the host worker does besides running jobs: dispatch, execute, watch, report."""

import asyncio
import contextlib
import logging
import threading
import time
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

import psycopg
from procrastinate import App
from procrastinate.exceptions import AlreadyEnqueued
from sqlalchemy import Engine, func, or_, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.config import Settings
from app.core import control
from app.db.models import Run, Task, WorkerStatus
from app.gateway import ledger
from app.gateway.procs import ProcRegistry
from app.gateway.router import Gateway
from app.gateway.types import utcnow
from app.workers import echo
from app.workers.queue import conninfo, run_task

log = logging.getLogger("aiorg.worker")
ACTOR = "worker"
CONTROL_STALE_S = 3.0  # halt (fail closed) when the stop flag is this old
CONTROL_RESTART_S = 10.0  # ...and restart the process if it stays unreadable this long
STUCK_JOB_S = 10.0  # an agent job `doing` with nothing executing it this long is released


def available_mb(meminfo: str | None = None) -> int:
    content = meminfo if meminfo is not None else Path("/proc/meminfo").read_text()
    for line in content.splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) // 1024
    return 0  # unknown counts as none: fail closed


def clear_dead_jobs(db: Session) -> int:
    """At startup, under the executor lock, every `doing` job belongs to a dead process. Close it
    so its lock is free; dispatch creates a fresh job from the task row if there is work left."""
    ids = list(
        db.scalars(text("select id from procrastinate_jobs where status = 'doing' order by id"))
    )
    for job_id in ids:
        db.execute(text("select procrastinate_finish_job_v1(:id, 'failed', false)"), {"id": job_id})
    db.commit()
    return len(ids)


class Supervisor:
    def __init__(
        self,
        settings: Settings,
        engine: Engine,
        app: App,
        gateway: Gateway | None,
        epoch: int,
        registry: ProcRegistry,
        free_mb: Callable[[], int] = available_mb,
        control_stale: Callable[[], float] = lambda: 0.0,
    ) -> None:
        self.settings, self.engine, self.app = settings, engine, app
        self.gateway, self.epoch, self.registry = gateway, epoch, registry
        self.free_mb = free_mb
        self.control_stale = control_stale  # seconds since the stop flag was last read
        self.active: dict[str, float] = {}  # task id -> monotonic start
        self._suspect: dict[int, float] = {}  # procrastinate job id -> first seen stuck
        self._low_ram_logged = False

    def _ram_ok(self) -> bool:
        ok = self.free_mb() >= self.settings.min_free_ram_mb
        if not ok and not self._low_ram_logged:
            log.warning("free memory below %d MB: not starting work", self.settings.min_free_ram_mb)
        self._low_ram_logged = not ok
        return ok

    # ---- running one task ------------------------------------------------------
    async def execute(self, task_id: str) -> None:
        """A job that cannot start now simply ends; dispatch creates a new one later."""
        if self.registry.halted() or not self._ram_ok() or task_id in self.active:
            return
        self.active[task_id] = time.monotonic()
        try:
            await asyncio.to_thread(self.work, task_id)
        finally:
            self.active.pop(task_id, None)

    def work(self, task_id: str) -> None:
        if self.registry.halted():  # stop or shutdown arrived after the job was accepted
            return
        # CLIs spawned from this thread are tagged with the task, so a cancel can kill them
        with Session(self.engine) as db, self.registry.owner(task_id):
            claimed = echo.claim_one(
                db, task_id=task_id, epoch=self.epoch, admit=lambda: not self.registry.halted()
            )
            if claimed is None:
                return
            if self.registry.wait(self.settings.echo_seconds):
                echo.hand_back(db, *claimed)  # halted before anything was sent
                return
            echo.finish(db, *claimed, self.gateway)

    async def sweep(self) -> None:
        def run() -> None:
            with Session(self.engine) as db:
                ledger.reconcile_stale(db, utcnow())

        await asyncio.to_thread(run)

    # ---- dispatch --------------------------------------------------------------
    def ready_to_dispatch(self, db: Session) -> list[str]:
        if self.registry.halted() or control.get(db).stopped or not self._ram_ok():
            return []
        busy = db.execute(
            text(
                "select count(*) from procrastinate_jobs "
                "where queue_name = 'agent' and status in ('todo', 'doing')"
            )
        ).scalar_one()
        slots = self.settings.agent_concurrency - busy
        if slots <= 0:
            return []
        queued = set(
            db.scalars(
                text(
                    "select lock from procrastinate_jobs "
                    "where status in ('todo', 'doing') and lock is not null"
                )
            )
        )
        ids = db.scalars(
            select(Task.id)
            .where(Task.status == "ready", or_(Task.retry_at.is_(None), Task.retry_at <= utcnow()))
            .order_by(Task.created_at)
            .limit(slots + len(queued))
        )
        return [i for i in ids if f"task:{i}" not in queued][:slots]

    async def dispatch(self) -> int:
        def pick() -> list[str]:
            with Session(self.engine) as db:
                return self.ready_to_dispatch(db)

        sent = 0
        for task_id in await asyncio.to_thread(pick):
            lock = f"task:{task_id}"
            try:
                await self.app.configure_task(
                    run_task.name, lock=lock, queueing_lock=lock, queue="agent"
                ).defer_async(task_id=task_id)
                sent += 1
            except AlreadyEnqueued:
                pass
        return sent

    # ---- health ----------------------------------------------------------------
    def orphans(self, db: Session, now: float) -> list[str]:
        """Tasks marked running, with an old run, that nothing here is executing. `active` is
        read BEFORE the query: a task that ends during it must not look orphaned."""
        active = set(self.active)
        cutoff = utcnow() - timedelta(seconds=self.settings.orphan_after_s)
        ids = db.scalars(
            select(Task.id)
            .join(Run, Run.task_id == Task.id)
            .where(Task.status.in_(control.ACTIVE), Run.status == "running")
            .group_by(Task.id)
            .having(func.max(Run.started_at) < cutoff)
        )
        return [i for i in ids if i not in active]

    def kill_cancelled(self, db: Session) -> int:
        """Kill the CLIs of tasks being executed here that are no longer active (a founder cancel
        or a stop from another process). The run is already closed, so nothing is trusted."""
        active = set(self.active)
        if not active:
            return 0
        live = set(
            db.scalars(select(Task.id).where(Task.id.in_(active), Task.status.in_(control.ACTIVE)))
        )
        db.rollback()
        return self.registry.kill_owned(active - live, self.settings.stop_grace_s)

    def release_stuck_jobs(self, db: Session, now: float) -> int:
        """A job left `doing` (its finish write failed) holds a slot and the task's job lock until
        a restart. Release one once nothing has executed its task for STUCK_JOB_S."""
        rows = db.execute(
            text(
                "select id, lock from procrastinate_jobs "
                "where queue_name = 'agent' and status = 'doing' order by id"
            )
        ).all()
        released, seen = 0, set()
        for job_id, lock in rows:
            if lock is not None and lock.removeprefix("task:") in self.active:
                continue
            seen.add(job_id)
            first = self._suspect.setdefault(job_id, now)
            if now - first >= STUCK_JOB_S:
                db.execute(
                    text("select procrastinate_finish_job_v1(:id, 'failed', false)"), {"id": job_id}
                )
                log.warning("released job %d left running with nothing executing it", job_id)
                released += 1
                seen.discard(job_id)
        self._suspect = {j: t for j, t in self._suspect.items() if j in seen}
        db.commit()
        return released

    def health(self, db: Session) -> str:
        """Every 2 s. Returns a reason if the process must restart, else ''."""
        self.beat(db)
        try:
            control.finish_stop(db, ACTOR)
        except OperationalError:  # busy: the next tick tries again
            db.rollback()
            log.warning("could not finish the emergency stop yet; retrying")
        self.kill_cancelled(db)
        self.release_stuck_jobs(db, time.monotonic())
        stale = self.control_stale()
        if stale > CONTROL_RESTART_S:
            return f"stop flag unreadable for {stale:.0f} s"
        lost = self.orphans(db, time.monotonic())
        if lost:  # recovery happens only at startup: restart to do it
            return f"{len(lost)} running task(s) with no execution"
        return ""

    def beat(self, db: Session) -> None:
        status = db.get(WorkerStatus, 1)
        if status is not None:
            status.heartbeat_at, status.in_flight = utcnow(), len(self.active)
            db.commit()

    async def run(self, stop: asyncio.Event) -> str:
        """Returns a reason if the process must restart; '' when asked to stop."""
        last_health = 0.0
        while not stop.is_set():
            await self.dispatch()
            if time.monotonic() - last_health >= 2:
                last_health = time.monotonic()

                def check() -> str:
                    with Session(self.engine) as db:
                        return self.health(db)

                reason = await asyncio.to_thread(check)
                if reason:
                    return reason
            try:
                await asyncio.wait_for(stop.wait(), timeout=0.5)
            except TimeoutError:
                pass
        return ""


def guard_lock(
    alive: Callable[[], bool], lost: Callable[[], None], every_s: float = 0.5
) -> threading.Event:
    """Own thread: losing the executor lock must end the process even if everything else is stuck.
    Set the returned event to stop guarding."""
    done = threading.Event()

    def watch() -> None:
        while not done.wait(every_s):
            if not alive() and not done.is_set():
                lost()
                return

    threading.Thread(target=watch, name="aiorg-lock-guard", daemon=True).start()
    return done


class ControlWatcher:
    """Own thread and connection, so a stop is acted on even if the event loop is stuck.
    If the control row cannot be read for a few seconds it halts (fail closed)."""

    def __init__(
        self,
        database_url: str,
        registry: ProcRegistry,
        grace_s: float,
        poll_s: float = 0.5,
    ) -> None:
        self.dsn, self.registry = conninfo(database_url), registry
        self.grace_s, self.poll_s = grace_s, poll_s
        self.generation: int | None = None
        self.last_ok = time.monotonic()
        self._conn: psycopg.Connection | None = None
        self._done = threading.Event()
        self._threads: list[threading.Thread] = []

    def stale_for(self) -> float:
        return time.monotonic() - self.last_ok

    def apply(self, stopped: bool, generation: int) -> None:
        new_stop = self.generation is not None and generation != self.generation
        self.generation = generation
        if stopped or new_stop:  # a new generation counts even if already resumed
            if new_stop or not self.registry.halted():
                log.warning("emergency stop: halting running work")
                self.registry.halt(self.grace_s)
        if not stopped:
            self.registry.reopen()

    def _read_once(self) -> None:
        """One poll. Never raises: the thread must outlive any error. `last_ok` only moves after
        the flag was read AND acted on; a missing row counts as unreadable."""
        try:
            if self._conn is None:
                self._conn = psycopg.connect(
                    self.dsn,
                    autocommit=True,
                    connect_timeout=2,
                    options="-c statement_timeout=1000",
                )
            row = self._conn.execute(
                "select stopped, generation from worker_control where id = 1"
            ).fetchone()
            if row is None:
                log.error("stop flag row is missing")
                return
            self.apply(row[0], row[1])
            self.last_ok = time.monotonic()
        except psycopg.Error as e:
            log.warning("cannot read the stop flag (%s)", type(e).__name__)
            self._drop_conn()
        except Exception as e:  # a bug here must not silently end stop handling
            log.error("stop flag check failed (%s)", type(e).__name__)
            self._drop_conn()

    def _drop_conn(self) -> None:
        conn, self._conn = self._conn, None
        if conn is not None:
            with contextlib.suppress(Exception):
                conn.close()

    def _read(self) -> None:
        while not self._done.is_set():
            self._read_once()
            self._done.wait(self.poll_s)

    def _deadman(self) -> None:
        while not self._done.wait(0.5):
            if time.monotonic() - self.last_ok > CONTROL_STALE_S and not self.registry.halted():
                log.error("stop flag unreadable: halting running work")
                self.registry.halt(self.grace_s)

    def start(self) -> None:
        self.last_ok = time.monotonic()
        for fn in (self._read, self._deadman):
            t = threading.Thread(target=fn, name=f"aiorg{fn.__name__}", daemon=True)
            t.start()
            self._threads.append(t)

    def close(self) -> None:
        self._done.set()
        for t in self._threads:
            t.join(timeout=5)
        self._drop_conn()
