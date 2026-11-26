# S04 escalation repair plan (fable, 2026-11-26). finding -> root cause -> fix -> test
H1 stop phase 2 fails after the fence -> only request_stop/resume/startup cancel; finish() then requeues,
   dead-letters or completes the run -> finish() re-reads the stop flag (plain read, after its task+run locks)
   before writing any outcome and cancels instead; supervisor health tick re-runs cancel_for_stop while stopped
   with active tasks; aiorgctl catches OperationalError like the API -> tests: reply/halt/429 while fence-only
   stop => cancelled; health tick cancels; ctl prints, exit 0, no traceback.
H2 watcher dead/connect-failing/row missing -> deadman halts forever, beat stays green -> reader catches every
   exception, missing row is an error, last_ok only after apply; Supervisor gets control_stale(); stale > 10 s
   => run() returns a restart reason -> tests: reader survives RuntimeError; missing row stays stale; run() exits.
M1 /transition cancel leaves Run running, CLI alive -> control.cancel_task(): run cancelled + role idle in the
   same tx; spawns tagged with the task (thread-local owner); health tick kills CLIs of tasks no longer active.
M2 retry counts never reset -> transient and crash counts only count runs started after the last task.retry.
M3 set_role_status unlocked read -> select role FOR UPDATE + populate_existing (lock order control,task,run,role).
M4 orphans() reads active after the query -> snapshot active before the query.
M5 job stuck `doing` -> health tick closes agent jobs `doing` whose task is not active for >= 10 s.
M6 kill during env_is_clean counted as sent -> precheck errors carry not_sent; router: Halted(sent) uses it.
M7 429 reset in the past/far future -> clamp to [now+60 s, now+24 h] in mark_rate_limited.
M8 ambiguous failure shown as "failed" -> AllRoutesFailed.maybe_sent; finish: effect unknown, reason
   call_maybe_sent with a "may have reached the provider" text in the UI.
M9 waiting tasks show only Ready -> requeue sets status_reason (waiting_quota / retry_transient); TaskOut gets
   retry_at; task card + detail show "Waiting until ...".
M10 silent route skips; type-only restart logs -> router logs skipped routes; host logs redacted type: message.
M11 echo --once ignores stop -> starts a ControlWatcher; gateway gets halted=REGISTRY.halted.
Codex-1 claim after shutdown halt -> claim_one(admit=...) re-checks the halt right before its commit.
Codex-2 lock_lost blocks on the Popen mutex -> ProcRegistry.halt_now(): flags + SIGKILL without the mutex.
Lows: gateway-host.sh uses host-env.sh; pin procrastinate==3.12.0; Halted(sent) from maybe-sent only (incl.
   the in-_attempt gate); not-sent ledger rows (halted, connect failure) excluded from limits; roles "today"
   uses day_tz; empty route -> "no route"; alive dot token; strengthen router concurrency + env-regex tests.
   Residual: worker.spec.ts:60 either-or (needs a seeded e2e failure; vitest covers the text); fuel.spec.ts:93
   does not exist (file has 57 lines). Founder design note stays a recorded risk.
Each fix: targeted regression test, run red before the fix where feasible; then full pytest, ruff, mypy,
vitest, eslint, tsc, API types regenerated.
