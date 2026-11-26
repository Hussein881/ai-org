# HANDOFF (state carried between fresh sessions; keep ≤60 lines; overwrite, don't append)

## Now
- Bootstrap: PARTIAL (2 items; see docs/state/bootstrap.md)
- Active slice: S04 `[~]` on slice/S04-worker (contains S03 `[~]`). NOT merged. Phase B
- The live worker (aiorg-worker.service) runs from this working tree. Leave it on slice/S04-worker

## Last session
- Ended with: CONTINUE S04 (reboot verified; reviews and 2 open items remain). Details: docs/state/slices/S04.md
- Done and live-verified: durable worker, kill -9 resume, emergency stop, queue across restart, dashboard
- Found: test_build_runner.py was switching branches in this repo (fixed)

## S04 reboot test: run 2026-11-26, passed (gaps in slices/S04.md: no task was queued at reboot)
- aiorg-worker is now enabled at boot. build-runner is disabled and must stay so (not approved)

## Remaining for S03 + S04 to reach `[x]`
- Codex's 2 open items (slices/S04.md); run /code-review, pr-review-toolkit, differential-review
- Then merge to main, tag phase-b-done, Notion milestone page

## Facts the next session needs
- Root setup: scripts/bootstrap/root-setup.sh (founder runs with sudo). Claude never uses sudo beyond D-036
- Secret status (names, SET/EMPTY only): /srv/aiorg/artifacts/secrets-status.txt
- Founder decisions: docs/state/FOUNDER_GATES.md. Worker log: /srv/aiorg/artifacts/logs/aiorg-worker.log
- Tests: postgres:17-alpine `aiorg-testpg` on 127.0.0.1:55433, AIORG_TEST_DATABASE_URL
- e2e: compose project aiorg-e2e with its own env file (127.0.0.1, API 8001, PG 55434) plus a fake-mode host
  worker against it; clear its model_usage first (5h call limit). LD_LIBRARY_PATH=~/.local/pwlibs/root/usr/lib/x86_64-linux-gnu

## Open issues / blockers
- S05 needs G4 (constitution), unanswered. S05 onward depends on it
- DEFERRED: build runner (slices/S00.md); installed units stale; keep stopped. Optional bubblewrap

## Founder decisions pending
- G1 answered. G3 ACCEPT-DEFAULTS. G4 constitution, G5 and G6 (only with P2/P-4), G7 backups. G2 N/A.

## Do not
- Don't run `sudo` (beyond D-036 lines) or read /srv/aiorg/secrets.
- Don't answer a founder gate on the founder's behalf.
