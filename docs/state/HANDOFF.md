# HANDOFF (state carried between fresh sessions; keep ≤60 lines; overwrite, don't append)

## Now
- Bootstrap: PARTIAL (2 items; see docs/state/bootstrap.md)
- Phase B done: S03 + S04 `[x]` (founder-accepted deferral), merged to main, tag phase-b-done. Not pushed
- Next slice: S05. It needs G4 (constitution): DRAFT in constitution/founder.md (uncommitted on purpose,
  from the founder interview 2026-11-26); founder hasn't said final -> NEEDS_FOUNDER S05 G4 until he does
- The live worker (aiorg-worker.service) runs from this working tree, now on main code (epoch 10)

## Last session
- S04 escalation repair (fable; session also reported opus-5-5) fixed most findings; Codex verification FAIL
- Founder: "Mark this as post implementation check and continue unless it affects functionality."
  Open items -> docs/state/plans/post-implementation-checks.md (re-check before S14; none breaks normal use)
- E2E 16 pass/1 skip/1 flaky (passed on rerun). Live API rebuilt, worker restarted, health 200

## Post-implementation checks (deferred, founder decision)
- docs/state/plans/post-implementation-checks.md: H1 stop fence, H2 watcher restart, M8 maybe-sent requeue first
- Founder priorities in the draft constitution: React dashboard creator, then easy create/delete of
  specialists: no slice covers these yet (plan via Project backlog after the core org)

## Facts the next session needs
- Root setup: scripts/bootstrap/root-setup.sh (founder runs with sudo). Claude never uses sudo beyond D-036
- Secret status (names, SET/EMPTY only): /srv/aiorg/artifacts/secrets-status.txt
- Founder decisions: docs/state/FOUNDER_GATES.md. Worker log: /srv/aiorg/artifacts/logs/aiorg-worker.log
- Tests: postgres:17-alpine `aiorg-testpg` on 127.0.0.1:55433, AIORG_TEST_DATABASE_URL
- e2e: compose project aiorg-e2e with its own env file (127.0.0.1, API 8001, PG 55434) plus a fake-mode host
  worker against it; clear its model_usage first (5h call limit). LD_LIBRARY_PATH=~/.local/pwlibs/root/usr/lib/x86_64-linux-gnu

## Open issues / blockers
- S05 needs G4 (constitution): draft ready, founder approval pending. S05 onward depends on it
- DEFERRED: build runner (slices/S00.md); installed units stale; keep stopped. Optional bubblewrap

## Founder decisions pending
- G1 answered. G3 ACCEPT-DEFAULTS. G4 constitution, G5 and G6 (only with P2/P-4), G7 backups. G2 N/A.

## Do not
- Don't run `sudo` (beyond D-036 lines) or read /srv/aiorg/secrets.
- Don't answer a founder gate on the founder's behalf.
