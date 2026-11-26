"""The host worker (ExecStart of aiorg-worker.service).

Exit code 0 only after a signal asked us to stop; anything else exits 1 so systemd restarts us.
"""

import asyncio
import logging
import os
import signal
import sys
import time
from collections.abc import Callable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core import control
from app.db.session import engine
from app.gateway.factory import build_gateway
from app.gateway.procs import REGISTRY, ProcRegistry
from app.gateway.redact import install_log_redaction, redact_text
from app.workers import echo, queue
from app.workers.lock import ExecutorLock
from app.workers.supervisor import (
    ControlWatcher,
    Supervisor,
    clear_dead_jobs,
    guard_lock,
)

log = logging.getLogger("aiorg.worker")
SCHEMA_HEAD = "0004"


def describe(error: BaseException) -> str:
    """Type and message for a restart log line, redacted (never just the type: say why)."""
    return redact_text(f"{type(error).__name__}: {error}")[:300]


def on_lock_lost(registry: ProcRegistry, exit_now: Callable[[int], object]) -> None:
    """Another executor may take over now: die at once. Never waits for the registry mutex (a
    hung spawn may hold it); systemd kills whatever is left in our cgroup."""
    registry.halt_now()  # first: nothing may be claimed, sent or spawned from here on
    log.error("executor lock lost: exiting")
    exit_now(1)


def _hard_exit(code: int) -> None:
    logging.shutdown()
    os._exit(code)


def wait_for_database() -> None:
    """Postgres (a rootless container) may come up after us at boot. Waiting is not a failure."""
    delay = 1.0
    while True:
        try:
            with engine().connect() as c:
                version = c.execute(text("select version_num from alembic_version")).scalar()
            if version is not None and version >= SCHEMA_HEAD:
                return
            log.info("waiting for database schema %s (now %s)", SCHEMA_HEAD, version)
        except Exception as e:  # not up yet; never log the URL
            log.info("waiting for the database (%s)", type(e).__name__)
        time.sleep(delay)
        delay = min(delay * 2, 10.0)


async def serve(lock: ExecutorLock) -> int:
    settings = get_settings()
    with Session(engine()) as db:
        epoch = control.bump_epoch(db)
        recovered = echo.reconcile(db)
        jobs = clear_dead_jobs(db)
        stopped = control.get(db).stopped
    log.info("recovery: %d task(s), %d dead job(s); stopped=%s", recovered, jobs, stopped)
    if stopped:
        REGISTRY.halt(settings.stop_grace_s)
    watcher = ControlWatcher(settings.database_url, REGISTRY, settings.stop_grace_s)
    gateway = build_gateway(halted=REGISTRY.halted) if settings.ceo_live_reply else None
    if gateway is not None:
        missing = [
            name
            for name, provider in gateway.providers.items()
            if gateway.policy.providers[name].enabled and not provider.available()
        ]
        if missing:  # visible in the log instead of silently skipped routes
            log.warning("enabled providers not reachable from this service: %s", ", ".join(missing))
    app = queue.make_app(settings.database_url)
    supervisor = Supervisor(
        settings, engine(), app, gateway, epoch, REGISTRY, control_stale=watcher.stale_for
    )
    queue.bind(supervisor)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()

    def on_signal() -> None:
        stop.set()
        REGISTRY.close(settings.stop_grace_s)  # close admission and signal CLIs right away

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, on_signal)

    guard = guard_lock(lock.alive, lambda: on_lock_lost(REGISTRY, _hard_exit))
    watcher.start()
    async with app.open_async():

        def queue_worker(name: str, concurrency: int) -> asyncio.Task[None]:
            return asyncio.create_task(
                app.run_worker_async(
                    queues=[name],
                    name=name,
                    concurrency=concurrency,
                    install_signal_handlers=False,
                    delete_jobs="successful",
                )
            )

        jobs_tasks = [
            queue_worker("agent", settings.agent_concurrency),
            queue_worker("system", 1),
        ]
        main_task = asyncio.create_task(supervisor.run(stop))
        log.info("worker ready (epoch %d, gateway %s)", epoch, settings.gateway_mode)
        done, _ = await asyncio.wait([main_task, *jobs_tasks], return_when=asyncio.FIRST_COMPLETED)
        code = 0
        if main_task in done:
            error = main_task.exception()
            reason = f"supervisor error: {describe(error)}" if error else main_task.result()
            if reason:
                log.error("restarting: %s", reason)
                code = 1
        else:
            errors = [describe(e) for t in done if not t.cancelled() and (e := t.exception())]
            log.error(
                "a queue worker stopped on its own: restarting (%s)",
                "; ".join(errors) or "no error",
            )
            code = 1
        if not stop.is_set() and code == 0:
            code = 1
        # shut down: no new work, SIGTERM the CLIs now, SIGKILL after the grace period
        REGISTRY.close(settings.stop_grace_s)
        deadline = time.monotonic() + settings.stop_grace_s + 10
        while supervisor.active and time.monotonic() < deadline:
            await asyncio.sleep(0.1)
        main_task.cancel()
        for t in jobs_tasks:
            t.cancel()
        await asyncio.wait([main_task, *jobs_tasks], timeout=10)
    guard.set()
    watcher.close()
    return code


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("procrastinate").setLevel(logging.WARNING)
    install_log_redaction()
    wait_for_database()
    lock = ExecutorLock(engine())
    waited = False
    while not lock.acquire():
        if not waited:
            log.info("another executor holds the lock; waiting")
            waited = True
        time.sleep(2)
    code = 1
    try:
        code = asyncio.run(serve(lock))
    except Exception as e:
        log.error("worker failed: %s", describe(e))
    finally:
        lock.release()
        logging.shutdown()
        sys.stdout.flush()
        sys.stderr.flush()
    os._exit(code)  # do not hang on a thread that is still unwinding


if __name__ == "__main__":
    main()
