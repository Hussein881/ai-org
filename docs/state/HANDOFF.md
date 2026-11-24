# HANDOFF (state carried between fresh sessions; keep ≤60 lines; overwrite, don't append)

## Now
- Bootstrap: PARTIAL (2 items; see docs/state/bootstrap.md)
- Active slice: S00 (status: needs founder; branch slice/S00-preflight, not merged)
- Phase: A
- Branch: main @ <commit>

## Last session
- Ended with: NEEDS_FOUNDER S00 (see docs/state/preflight.md)
- Did: G3 recorded; scaffold, runner (tested), keycheck + 3 units written (not installed), K1-K12/K14-K16/K18/K19(diff-review)/K21/K22 installed; settings allowlist NOT extended (blocked)
- Remaining in this slice (if CONTINUE): n/a

## Facts the next session needs (not derivable from code in 1 minute)
- Root setup is done by `scripts/bootstrap/root-setup.sh` (founder runs it with sudo). Claude never uses sudo.
- Secret status (names, SET/EMPTY only): /srv/aiorg/artifacts/secrets-status.txt
- Founder decisions live in docs/state/FOUNDER_GATES.md (G1 to G7).
- Host is Ubuntu 26.10; Python 3.12 is uv-managed for aiorg (D-037).
- Root access for aiorg is only the sudoers rule in /etc/sudoers.d/aiorg (D-036). Services are system units with User=aiorg; build sessions must pass scripts/check-env-clean.sh.

## Open issues / blockers
- Needs Anwar: real origin URL + first push; constitution interview (before S05); optional bubblewrap

## Founder decisions pending
- G1 YES-ALL; K13/K17/K20/K19b pending founder after scan (preflight.md). G3 ACCEPT-DEFAULTS. G4 constitution (career only when backlog P2 is added), G5 (P-3, only with P2), G6 (P-4), G7 backups. G2 N/A (rootless PASS).

## Do not
- Don't run `sudo` or read /srv/aiorg/secrets.
- Don't answer a founder gate on the founder's behalf.
