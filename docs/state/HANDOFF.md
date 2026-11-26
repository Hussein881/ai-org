# HANDOFF (state carried between fresh sessions; keep ≤60 lines; overwrite, don't append)

## Now
- Bootstrap: PARTIAL (2 items; see docs/state/bootstrap.md)
- Active slice: S04 (in progress). S03 is `[~]` on slice/S03-gateway, NOT merged; branch S04 from it
- Phase: B
- Branch: slice/S03-gateway. WARNING: check `git branch --show-current` before every commit (unexplained checkouts seen twice)

## Last session
- Ended with: CONTINUE (checkpoint). S03 built and live-verified; see docs/state/slices/S03.md
- Did: gateway, ledger, quotas, 5 live providers verified, fuel gauges; 139 pytest, 13 Playwright
- Remaining: S04 host worker closes S03's open HIGH; then run /code-review, pr-review-toolkit, differential-review + Codex on S03+S04; merge
- e2e: `docker compose -p aiorg-e2e --env-file <own env> up` with AIORG_BIND_IP=127.0.0.1, AIORG_API_PORT=8001, AIORG_PG_PORT=55434; LD_LIBRARY_PATH=~/.local/pwlibs/root/usr/lib/x86_64-linux-gnu. Test DB: postgres:17-alpine on 127.0.0.1:55433, AIORG_TEST_DATABASE_URL
- Gates: S05 needs G4 (constitution), still unanswered
- S04 reboot test needs a human watching: it ends the session

## Facts the next session needs (not derivable from code in 1 minute)
- Root setup is done by `scripts/bootstrap/root-setup.sh` (founder runs it with sudo). Claude never uses sudo.
- Secret status (names, SET/EMPTY only): /srv/aiorg/artifacts/secrets-status.txt
- Founder decisions live in docs/state/FOUNDER_GATES.md (G1 to G7).
- Host is Ubuntu 26.10; Python 3.12 is uv-managed for aiorg (D-037).
- Root access for aiorg is only the sudoers rule in /etc/sudoers.d/aiorg (D-036). Services are system units with User=aiorg; build sessions must pass scripts/check-env-clean.sh.

## Open issues / blockers
- DEFERRED: finish build runner (open defects in slices/S00.md), re-review, re-install units, run keycheck. Installed units are stale; keep build-runner stopped. Needs Anwar: constitution interview (before S05); optional bubblewrap

## Founder decisions pending
- G1 fully answered (YES-ALL + K13/K17/K20/K19b). G3 ACCEPT-DEFAULTS. G4 constitution (career only when backlog P2 is added), G5 (P-3, only with P2), G6 (P-4), G7 backups. G2 N/A (rootless PASS).

## Do not
- Don't run `sudo` or read /srv/aiorg/secrets.
- Don't answer a founder gate on the founder's behalf.
