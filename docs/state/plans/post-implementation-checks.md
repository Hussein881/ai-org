# Post-implementation checks (founder decision 2026-11-26)
Founder: "Mark this as post implementation check and continue unless it affects functionality."
Items an independent review left open, deferred so the build can continue. None breaks normal operation
(each needs a rare timing window or a DB/process failure). Re-check each before FINAL_REPORT (S14); fix, or
keep as accepted risk with the founder's OK. If one is seen in real operation, it stops being deferred.

## From S04 escalation verification (Codex gpt-6.2-sol, static; slice record S04.md)
Priority order: the first three matter most for unattended running.
1. H1: an outcome can commit after the stop fence (plain read of `stopped` before completion/requeue);
   echo.py:298. Effect: in a sub-second window a task finishes or requeues after Emergency stop.
2. H2: stale-watcher restart can stall behind kill_cancelled + spawn mutex with a hung spawn;
   supervisor.py:225. Effect: after a DB failure plus a hung CLI spawn, no self-restart.
3. M8: timeout then quota block returns Queued and requeues a maybe-sent call; a data-class refusal on
   another route can mask maybe_sent; router.py:195. Effect: possible duplicate (paid) call.
4. New: failed halt consumes a stop generation (apply records it before halting); supervisor.py:302.
5. M5: stuck-job cleanup can race normal Procrastinate finalization; supervisor.py:205.
6. M7: existing far-future blocked_until survives the clamp (ledger.py:255); huge Retry-After can
   overflow (providers/live.py:144).
7. Codex-1: shutdown between admission check and claim commit (echo.py:77); task is handed back unsent.
8. New: per-task cancel during the CLI env precheck can still launch the CLI (providers/live.py:66).
9. Tests: router reservation test timing-dependent (test_gateway_router.py:271); waiting-note UI
   rendering, disabled-route logging, `--once` CLI kill untested (test_worker_repair.py:449);
   worker.spec.ts:60 either-or assertion; tasks.spec.ts:42 flaky in parallel runs (another spec's emergency
   stop halts its run; passed on rerun, artifacts/review/S04-e2e*.txt).

## Earlier accepted residuals (unchanged)
SIGTERM path still takes the process mutex (bounded by systemd stop timeout). Founder design note:
the key-holding service runs working-tree code (S00, needs founder acceptance).
