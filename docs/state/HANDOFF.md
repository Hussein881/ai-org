# HANDOFF (state carried between fresh sessions; keep ≤60 lines; overwrite, don't append)

## Now
- Bootstrap: PARTIAL (2 items; see docs/state/bootstrap.md)
- Active slice: S04 `[!]` BLOCKED (contains S03 `[!]`). NOT merged. Phase B
- Repair attempt lives on branch slice/S04-repair (worktree .claude/worktrees/s04-repair, 3716097); NOT merged
- The live worker (aiorg-worker.service) runs from this working tree. Leave it on slice/S04-worker

## Last session
- Ended with: BLOCKED S04. Escalation repair (fable) fixed most findings (220 tests pass) but Codex verification
  FAILED: H1, H2, M5, M7, M8, Codex-1, router test open + 2 new. Record: slice/S04-repair:docs/state/slices/S04.md
- G4: constitution DRAFT in constitution/founder.md (uncommitted on purpose); founder hasn't said final

## S04 reboot test: run 2026-11-26, passed (gaps in slices/S04.md: no task was queued at reboot)
- aiorg-worker is now enabled at boot. build-runner is disabled and must stay so (not approved)

## Remaining for S03 + S04 to reach `[x]`
- Escalation budget used (MODEL_POLICY rules 2-3). Founder must decide: authorize another repair round on
  slice/S04-repair (new context: Codex's list), accept specific residuals, or re-scope. Then Codex verify, merge

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
