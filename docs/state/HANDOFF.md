# HANDOFF (state carried between fresh sessions; keep ≤60 lines; overwrite, don't append)

## Now
- Bootstrap: NOT RUN (run `/bootstrap` first; see docs/BOOTSTRAP.md)
- Active slice: S00 (status: not started)
- Phase: A
- Branch: main @ <commit>

## Last session
- Ended with: <none yet>
- Did: package placed in its final layout (v2.1); v2.2 setup fixes (D-036 services/secrets/sudoers, D-037 uv Python)
- Remaining in this slice (if CONTINUE): n/a

## Facts the next session needs (not derivable from code in 1 minute)
- Root setup is done by `scripts/bootstrap/root-setup.sh` (founder runs it with sudo). Claude never uses sudo.
- Secret status (names, SET/EMPTY only): /srv/aiorg/artifacts/secrets-status.txt
- Founder decisions live in docs/state/FOUNDER_GATES.md (G1 to G7).
- Host is Ubuntu 26.10; Python 3.12 is uv-managed for aiorg (D-037).
- Root access for aiorg is only the sudoers rule in /etc/sudoers.d/aiorg (D-036). Services are system units with User=aiorg; build sessions must pass scripts/check-env-clean.sh.

## Open issues / blockers
- none yet

## Founder decisions pending
- G1 answered YES-ALL; K13/K17/K20 pending S00 scan report. G3 envelopes, G4 constitution (career only when backlog P2 is added), G5 (P-3, only with P2), G6 (P-4), G7 backups. G2 only if rootless Docker fails.

## Do not
- Don't run `sudo` or read /srv/aiorg/secrets.
- Don't answer a founder gate on the founder's behalf.
