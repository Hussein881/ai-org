# S04 plan: durable worker and restart safety (T2)

Sources: feature-dev code-explorer (Procrastinate 3.12.0 internals) and code-architect (opus).

## Approach
Procrastinate host worker plus an in-process supervisor loop. Our tables stay the source of truth for tasks;
Procrastinate supplies job locks, backoff retries, heartbeats, stalled detection and periodic jobs.
After kill -9 a job stays `doing` and keeps its lock; nothing requeues it, so recovery is ours.

## New files
- `migrations/procrastinate/schema-3.12.0.sql` (vendored) + `migrations/versions/0004_worker.py`
  (`execute_script`; `external_effect`, `worker_control` single row, `tasks.status_reason`).
- `app/workers/queue.py`: Procrastinate app; `run_task(task_id)` queue `agent`,
  `RetryStrategy(max_attempts=2, exponential_wait=10, retry_exceptions={TransientRetry})`;
  periodic `sweep` queue `system` (stale reservations, orphaned runs).
- `app/workers/supervisor.py`: 1 s tick, no Procrastinate lock: watch_control, recover_stalled
  (heartbeat > 30 s: abandon run, task ready, retry_job; 3rd stall -> failed_execution `crash_loop`),
  dispatch (not stopped, MemAvailable >= 1536 MB, <= 2 active; lock and queueing_lock `task:<id>`),
  reconcile_orphans.
- `app/workers/host.py`: waits for DB + schema forever; two Procrastinate workers (agent concurrency 2,
  system 1); SIGTERM: drain 25 s then terminate CLIs; exit 0 only after a signal, else 1.
- `app/workers/effects.py`: external_effect begin/done/failed/unknown/supersede; key `{task}:ack#{n}`.
- `app/core/control.py`: stop (running/verifying -> cancelled with reason; runs cancelled = fence),
  resume; ready tasks stay ready but paused.
- `app/gateway/procs.py`: process registry; own process group per CLI; SIGTERM, SIGKILL after 30 s.
- `app/api/admin.py`: status (alive = heartbeat < 30 s), stop, resume, dead-letter list and retry (CSRF).
- `app/ctl.py` + `scripts/aiorgctl`: stop | resume | status.
- Web: WorkerDot, StopButton (alert dialog), /dead-letter page.

## Changes
- subproc.run_cli: Popen + registry; refuses to spawn while closing/halted.
- Gateway: `halted()` checked before each candidate and after each failure -> `Halted`, no fallback.
- echo.finish: keeps `_lock_owned`; before a model call reads the effect: done -> reuse saved reply, no call;
  another run's `intent` -> mark unknown, fail `effect_unknown` (dead-letter); else write intent, commit,
  call, save `done` in its own commit. AllRoutesFailed with retries left -> task ready, TransientRetry.
- API echo loop: off by default in compose, and never claims or reconciles while a worker heartbeat is fresh.
- fake provider: optional delay via a real `sleep` subprocess; crash points honoured only in fake mode.
- run-worker.sh: reads only POSTGRES_PASSWORD and AIORG_PG_PORT from .env (no `set -a` sourcing);
  live gateway; exec host worker; keeps the smoke-request branch.

## "No duplicate effect", honestly
- Killed before the intent: resumes, 1 call. Killed after `done`: completes from saved reply, 1 call.
- Killed while the call is in flight: outcome unknowable. NOT re-run; dead-letter. Only the founder's
  Retry allows a second call. So "resumes once" holds for the other windows; this one stops for a human.

## Failure matrix (short)
DB down at boot: wait. DB lost mid-run or worker returns unexpectedly: exit 1, systemd restarts.
Crash loop: capped by our own count. Low RAM: stays ready. Stop while worker down: DB flag holds, resume
is explicit and survives reboot. Duplicate dispatch: queueing_lock + active check + row lock.
Residual: `systemctl stop` during a call over 25 s leaves it `unknown` (dead-letter).
Transient retries can make up to 3 calls for one CEO ack (AUTONOMY: max 2 retries).

## Tests
Unit: registry TERM/KILL incl. grandchild; spawn refused when closing; meminfo; Halted no fallback.
Integration: migration; dispatch (idempotent, retry_at, stopped, RAM, cap 2); transient exhaustion;
effect states; stalled recovery + cap; admin API auth/CSRF/stop/resume/dead-letter; echo-loop guard.
Crash (real processes, real kill -9): each crash point then restart; emergency stop within 5 s with a
TERM-ignoring child; concurrency <= 2; exit codes. Web: Vitest + Playwright.
Live: systemd restart -> green dot; kill the worker mid-task; reboot test (founder watching).

## Revision 1 (after Codex plan review round 1: FAIL, 12 findings). Overrides anything above that conflicts.
R1 One executor. Anything that claims or reconciles tasks holds a Postgres session advisory lock. The host
   worker takes it for its whole life on a dedicated connection and calls os._exit(1) if that connection
   fails (systemd's control-group kill removes its CLI children). The API echo loop and `echo --once`
   take it per step with pg_try_advisory_lock and do nothing if they cannot.
R2 Jobs are disposable; tasks are the only truth. Never retry_job a stalled job; no heartbeat-based
   takeover. After taking the lock, before any Procrastinate worker starts, recovery (idempotent steps):
   (a) running/verifying task: running runs -> `crashed`; 3rd crashed run -> failed_execution `crash_loop`,
   else ready; (b) any other `running` run -> abandoned; (c) every `doing` job is finished as failed.
   dispatch then creates a fresh job. Covers kill before claim (task ready), after completion
   (task completed: only the job is closed) and during recovery (rerun).
   Live process: a task `running` but not in the in-memory active set, or a `doing` job older than 60 s
   with no active execution, is recovered the same way.
R3 Lock order: worker_control -> task -> run -> role. claim_task takes control FOR SHARE and refuses when
   stopped; request_stop takes control FOR UPDATE (lock_timeout 4 s), then tasks ordered by id. So a claim
   either commits first and is cancelled by stop, or sees the stop. Every outcome write, including
   _abandon, happens under the task+run locks and only if run.status == running.
R4 Stop: worker_control.generation increments per stop. A dedicated watcher THREAD (own connection, 0.5 s
   poll, statement_timeout 1 s) acts on any generation change, so stop+quick resume is still seen.
   If it cannot read control for 3 s it fails closed (halt admission, terminate). ProcRegistry holds one
   mutex over (halted check + spawn) and (set halted + snapshot of processes), so no spawn slips past.
   SIGTERM to the groups at once, SIGKILL after 30 s; processes spawned after resume are not in the
   snapshot. HTTP API calls in flight cannot be signalled: bounded by their timeout, result discarded by
   the run fence. cancelled stays terminal (founder creates a new task).
R5 Shutdown: SIGTERM closes admission and TERMs CLI groups immediately (no drain), KILL at 30 s.
R6 Retries: every outbound attempt is already journaled (model_usage reservation before the call).
   Only proven no-effect transient failures retry: HTTP 500/502/503/529 and connect errors (request never
   sent). timeout, killed, cli_error, other network and malformed are ambiguous: failed_execution ->
   dead-letter. AllRoutesFailed carries `retryable` = every attempted route failed that way. Budget: our
   own count of runs with status `transient` (max 2), independent of job attempts and crash count.
   RetryStrategy is not relied on: retry = task ready + retry_at (10 s, 60 s), dispatched by the supervisor.
   external_effect is the task-level record around the whole gateway call (intent/done/failed/unknown);
   model_usage is the per-attempt record. An `intent` found from another run -> unknown -> dead-letter.
R7 Completion unchanged: output + check record + run + task in one commit under the run fence; replay is a
   no-op because the run is no longer `running`.
R8 Ledger: reconcile_stale selects FOR UPDATE SKIP LOCKED with outcome='reserved'; finalize locks the row.
   A late finalize may still replace `abandoned` with the real outcome (more accurate, same commit as event).

## Revision 2 (after plan review round 2: FAIL, 8 findings). Overrides earlier text. NOT re-reviewed as a plan.
P1 Executor epoch: after taking the advisory lock every entry point (host, echo loop, --once) bumps
   worker_control.epoch (row FOR UPDATE), then recovers. claim_task refuses unless its epoch is current.
   Old executors are fenced from claiming by epoch and from writing by run.status (recovery ends their runs).
P2 No live orphan recovery. A task `running` with no in-memory execution for > 60 s makes the host exit 1;
   startup recovery is the only recovery path (runs before any job is fetched).
P3 A task with a `done` effect is replayed: the crash cap rises to 6 for it.
P4 Stop = two commits. First: control only (stopped, generation+1): the admission fence. Second: lock all
   running tasks, then their runs, then write roles. Startup recovery finishes the second if stopped.
   Watcher: connect_timeout 2 s, statement_timeout 1 s; a separate timer halts if no successful read for 3 s.
   The gateway also checks halted() immediately before provider.call, after the reservation.
P5 Effect resolution on failure (failed/unknown) commits together with the run outcome and task change.
   Only `done` (the saved reply) commits on its own.
P6 /api/tasks/{id}/transition failed_execution -> ready uses the same audited retry as dead-letter
   (supersedes unknown/intent effects).
Not accepted: "stop routing on any ambiguous failure". A model call changes nothing outside the system; its
effect is quota, which the ledger reserves per attempt, and S03's acceptance requires the fallback chain.
The automatic task-level retry stays limited to connect errors and 500/502/503/529 (AUTONOMY: max 2).
