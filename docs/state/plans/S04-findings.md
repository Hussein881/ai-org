# S03+S04 result review findings, 2026-11-26 (input for the next repair; nothing fixed yet)
Reviewers (all Claude, separate contexts, read-only, nothing executed): differential-review (opus) PASS_WITH_NOTES;
silent-failure-hunter FAIL; pr-review-toolkit code-reviewer PASS_WITH_NOTES; /code-review medium (unverified
by it). Full security report: artifacts/review/S04-differential.md (gitignored).
"Checked" = the main session (the implementer, not independent) re-read the code path. None reproduced by test.

## High (checked)
H1 Stop phase two failing (OperationalError after the fence commit) is never retried by a live worker
   (cancel_for_stop only from request_stop; resume and startup cancel too). The halted worker then requeues
   or dead-letters the run, so it escapes cancel and a requeued one runs after Resume; an in-flight HTTP
   reply can complete it while stopped. API says stopped; aiorgctl tracebacks. admin.py:79, echo.py:250-261.
H2 Watcher persistently failing (connect only, non-psycopg error kills thread, missing row): registry stays
   halted, supervisor keeps beating: green dot, nothing dispatched, no restart. supervisor.py.

## Medium / important (checked)
M1 Single-task cancel via /transition leaves Run running; pre-send check reads Run only; CLI not signalled (4/4
   area, 3 reviewers). tasks.py:117, echo.py:114
M2 founder Retry resets neither transient nor crash counts. echo.py:188,315
M3 Role can show Idle while running: set_role_status reads unlocked. tasks.py:25
M4 orphans() reads self.active after the query: a task finishing in between forces a needless restart.
M5 Procrastinate job left `doing` (finish write failed) is never detected live; holds slot + lock.
M6 Kill during env_is_clean() precheck counts as sent -> effect_unknown. subproc.py, router.py
M7 429 reset in the past -> immediate requeue, no cap; no upper bound either (a far date blocks for good).
M8 Ambiguous timeout/killed/cli_error/network: effect `failed`, text "Every model provider failed", no
   "may have been sent" warning before Retry. reasons.ts, echo.py:238
M9 Waiting tasks show only Ready (no status_reason on requeue; resets_at not shown).
M10 Unavailable/disabled routes skipped without log; restart logs keep only the exception type.
M11 `echo --once` has no ControlWatcher/halted: stop does not kill its CLI.

## Low (checked)
gateway-host.sh sources all of .env (run-worker.sh calls it under the key-holding unit for smoke).
procrastinate not pinned to ==3.12.0 while its schema is vendored. Halted(sent=bool(failures)) counts
not-sent failures as sent (fails safe).

## Low (reported, not re-checked)
Unsent calls use call-count limits; roles.py "today" is UTC not day_tz; empty route list -> 500; alive dot
raw palette class; latent Halted(sent=False) after earlier ambiguous attempt; weak tests: worker.spec.ts:60,
test_gateway_router.py:259, fuel.spec.ts:93 (flaky), test_gateway_core.py:127.

## Design note for the founder (from S00, not this diff)
The key-holding service runs code from the working tree, and build sessions may restart it: a build session
could run its own code with the provider keys despite D-036.
