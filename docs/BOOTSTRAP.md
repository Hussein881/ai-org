# Bootstrap: Claude Code finishes the server setup (runs before S00)
Run by Claude Code as user `aiorg` in `~/ai-org`, **interactively, with the founder watching**. Started by `/bootstrap` or the first prompt in `docs/SETUP.md`. It does everything in SETUP that doesn't need the founder's hands, checks the hands-on items he has already done, and lists exactly what's still missing. It is not a slice: no branch, no review, no TASKS marker.

## Rules for this session
- **Never run `sudo`** here. The narrow sudoers rule (D-036) exists for later slices; bootstrap needs none of it except the read-only `sudo -n -l`. If a step needs root, write the exact command into the report under "Needs Anwar" and move on.
- **Never read `/srv/aiorg/secrets/`** (it is root-only anyway). Key status comes only from `/srv/aiorg/artifacts/secrets-status.txt`, which holds names and SET/EMPTY, no values. Never print, echo or log a secret.
- **Pre-approved changes outside the repo, for bootstrap only** (the founder approved these by starting bootstrap): rootless Docker for `aiorg` (`~/.config/systemd/user/`, `~/.local/share/docker`), one `DOCKER_HOST` line in `~/.bashrc`, `~/.gitconfig`, `~/.ssh/known_hosts` entry for github.com, uv's managed Python 3.12 (`~/.local/share/uv`, D-037). Nothing else outside `~/ai-org` and `/srv/aiorg`.
- Don't decide anything in `docs/state/FOUNDER_GATES.md`. You may record an answer only when the founder types it in this session.
- Don't install plugins or skills here; S00 does that under gate G1.
- Keep going past failures: record each one and continue with the next check. Stop early only at B1 failures.

## Steps (record each as PASS / FAIL / NEEDS ANWAR with a one-line reason)
**B1. Identity and billing safety (stop if any fails).** `whoami` is `aiorg`; working dir is `~/ai-org`; `bash scripts/check-env-clean.sh` prints `ENV_CLEAN` (no API key or token variable in this shell, or the build bills the API instead of the subscription and the model could see keys; names only are printed). Also record `sudo -n -l` output: PASS if it lists the AI Org systemctl commands and nothing broader (the rule from root-setup.sh), NEEDS ANWAR if missing.

**B2. Machine.** OS release; `nproc`; `free -h`; `df -h /` (warn under 30 GB free); `timedatectl show -p NTPSynchronized`; `getent hosts github.com api.anthropic.com`; `tailscale status` (PASS if the Lenovo shows as logged in; note its Tailscale name); `ss -ltn` (note anything already on 80, 443, 5432, 8000).

**B3. Toolchain.** `git --version`; `uv --version`; `uv python find 3.12` (Python 3.12 is uv-managed, D-037; the system Python is not used; if it finds none, run `uv python install 3.12` (pre-approved) and re-check); `node -v` (≥20); `npm -v`; `docker --version`; `docker compose version`; `claude --version`; `codex --version`.

**B4. Rootless Docker.** If `docker info` already works as `aiorg` without the docker group, PASS. Otherwise:
1. `dockerd-rootless-setuptool.sh install` (needs `XDG_RUNTIME_DIR=/run/user/$(id -u)`; if it's unset, the founder logged in with `sudo su` instead of SSH: record NEEDS ANWAR "log in as `ssh aiorg@<lenovo>`" and skip B4).
2. `systemctl --user enable --now docker`; append `export DOCKER_HOST=unix:///run/user/$(id -u)/docker.sock` to `~/.bashrc` if not present, and export it for this session.
3. Verify `docker run --rm hello-world` and `docker compose version`.
If it PASSES, write `Answer: N/A (rootless Docker PASS in bootstrap, <date>)` under **G2** in FOUNDER_GATES (the founder pre-authorized exactly this on 2026-11-24). If it still fails, record FAIL with the error, and mark gate **G2** in FOUNDER_GATES as "needed: rootless failed because <reason>". Do not try the docker group.

**B5. CLI sign-ins.**
- Claude: `claude -p "reply with the word ok" --model haiku --output-format json` returns a result. Record the plan tier if shown (`claude /status` is interactive; ask the founder to read it off if needed).
- Codex: `codex login status`. If not signed in: NEEDS ANWAR "run `codex login --device-auth` (or see `codex login --help`)". If signed in, also run `codex exec --sandbox read-only "reply with the word ok"` and record the model it reports.

**B6. Secrets present.** Read `/srv/aiorg/artifacts/secrets-status.txt`. If missing: NEEDS ANWAR "fill the two env files, then (as the admin user) `sudo bash /home/aiorg/ai-org/scripts/bootstrap/root-setup.sh --check-secrets`". Report each variable SET/EMPTY. Required before S03: `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`. Required before S05: `NOTION_TOKEN`, `NOTION_INBOX_DB_ID`. Optional: `OPENROUTER_API_KEY`, `NTFY_*`. From the owner/mode lines in the same file, check the secrets dir is `root` mode `700` and each env file is `root` mode `600` (`aiorg` can't stat inside the dir itself). (Live key tests are S00's job, per PROVIDERS §What S00 must verify.)

**B7. Git.**
1. `git config --global init.defaultBranch main`, `user.name "AI Org Builder"`, `user.email "aiorg@$(hostname)"` (only if unset).
2. If `~/ai-org` has no `.git`: `git init`. Before the first commit, scan for secret-looking strings (`grep -rEn "sk-ant-[A-Za-z0-9_-]{20}|sk-or-[A-Za-z0-9_-]{20}|AIza[0-9A-Za-z_-]{30}|ntn_[0-9A-Za-z]{20}|ghp_[A-Za-z0-9]{30}|-----BEGIN [A-Z ]*PRIVATE KEY" --exclude-dir=.git .`; each pattern needs a key body, so this line doesn't match itself); any hit is a FAIL and nothing is committed. Then commit everything as `chore: v2.2 plan package (bootstrap)`.
3. GitHub: `ssh-keyscan -t ed25519 github.com` and confirm `ssh-keygen -lf` shows `SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU` (GitHub's published key) before adding it to `~/.ssh/known_hosts`. Then `ssh -T git@github.com` (a "successfully authenticated" message is PASS even though it exits 1).
4. Ask the founder for the repo's SSH URL (`git@github.com:<owner>/<repo>.git`) if `origin` isn't set. `git remote add origin <url>`; `git push -u origin main`. If the deploy key isn't added yet: NEEDS ANWAR and continue.

**B8. Founder gates.** Read `docs/state/FOUNDER_GATES.md`. List every gate with its answer or "unanswered", and the slice it blocks. If the founder answers any in this session, write the answer and date into the file. Never fill one in yourself.

**B9. Constitution (optional now, required before S05).** Offer: "Want me to interview you now to draft `constitution/founder.md`? About 10 minutes." (`config/career.yaml` waits until the Career project is added, D-038.) If yes, ask a few questions at a time following the templates in those files, write the drafts, and show them. The founder approves or edits them; mark G4 answered only when he says they're final.

**B10. Report and handoff.**
1. Write `docs/state/bootstrap.md`: a table of B1 to B9 with PASS/FAIL/NEEDS ANWAR; machine facts S00 will need (Tailscale name, Docker mode, Python/Node versions, Codex model); a short **Needs Anwar** checklist with exact commands; and the unanswered gates.
2. Update `docs/state/HANDOFF.md`: "Bootstrap: DONE | PARTIAL (n items)", active slice S00 not started, the Needs-Anwar items under Open issues, unanswered gates under Founder decisions pending.
3. Commit (`chore: bootstrap report`) and push if `origin` works.
4. Print the Needs-Anwar list, the unanswered gates, and the S00 prompt from `docs/SETUP.md` Part C. Tell the founder to `/exit` and start S00 in a fresh session once the list is empty (or once only items S00 can live with remain: G2 to G7 can still be open at S00).
5. Last line: `BOOTSTRAP_DONE` or `BOOTSTRAP_PARTIAL <n>`.

Re-running bootstrap is safe: it re-checks everything and overwrites `docs/state/bootstrap.md`.
