# HANDOFF (state carried between fresh sessions; keep ≤60 lines; overwrite, don't append)

## Now
- Bootstrap: PARTIAL (2 items; see docs/state/bootstrap.md)
- Active slice: S03 (not started; run by hand, runner stays stopped). S00, S01, S02 are on main (S01/S02 reviews partial)
- Phase: A done (tag phase-a-done) -> Phase B
- Branch: main

## Last session
- Ended with: S02 merged; stack running via docker compose (api+postgres healthy). Records: docs/state/slices/S01.md, S02.md
- Did: tasks + state machine, SSE, echo worker, Tasks board, live org chart; 43 pytest + 9 Playwright pass; Codex review FAIL x3 with fixes, 2 accepted SSE edge cases
- Mistake fixed: S02 commits had landed on slice/S01-walking-skeleton; merged to main afterwards and tag moved
- Cookie: plain http over the tailnet accepted (AIORG_COOKIE_SECURE=false); HTTPS/tailscale serve not needed
- e2e needs LD_LIBRARY_PATH=~/.local/pwlibs/root/usr/lib/x86_64-linux-gnu (Chromium libs extracted without root)
- Founder should change the password: `uv run python -m app.cli set-password` in a real terminal, then `docker compose up -d`

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
