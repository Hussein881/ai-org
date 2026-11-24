# Autonomous Execution and Approval Policy
Applies to two actors: the **builder** (Claude Code run by the build runner) and the **organization** (agents at runtime). Backend and `.claude/settings.json` enforce these rules; prompts only explain them.

## §Pre-approved (no founder checkpoint)
Builder: plan and revise implementation details within a slice; create/edit files in the repo; branches, commits, merges of reviewed slices to `main`; run tests, linters, type checks; start/stop the project's own containers and services; reversible migrations on the project's own database; install Python packages listed in `pyproject.toml`; call models within subscription windows; bounded repairs; continue through all slices; write reports; post status items to the Notion inbox; the exact root commands in `/etc/sudoers.d/aiorg` (start/stop/restart of `aiorg-worker` and `build-runner`, start of `aiorg-keycheck`, and `systemctl reboot` for S04's reboot test only) (D-036).
Organization: run approved pipelines on schedule; create/assign tasks within approved departments; CEO-approved routine plans; minor role-instruction changes (CEO-classified, logged, founder can reverse); draft (never send) outreach; write briefings and reports; use free-tier and subscription providers within envelopes.

## §Needs founder authorization
New permissions, credentials or providers; **any paid API usage beyond the approved $30/month Anthropic cap (D-027)**, or on any other paid provider; raising any limit or envelope; changing governance, approval policy, chain of command or the Constitution (except via founder correction); opening ports or exposing anything beyond Tailscale; modifying files or services outside the repo and `/srv/aiorg`; destructive operations on persistent data (drops, deletes, force-push, history rewrite); significant architecture replacement (e.g. leaving the fixed stack); installing executable skills or plugins not already approved; disabling QA, security or gates; adding a department; sending anything outside the system on the founder's behalf (applications, messages, emails); CEO-classified **major** pipeline changes; Board Advisor strong disagreement.

## §Default limits (founder-tunable in policy)
- Build: repair rounds per CLAUDE.md tiers; max 4 continuations per slice; 1 concurrent Claude Code session.
- Runtime: max 2 retries for transient provider errors with exponential backoff; usage-window exhaustion queues work until reset (not a failure); 2 concurrent CLI agent processes from S04 (free-RAM guard ≥1.5 GB), 3 if S13 shows headroom.
- Envelopes from MODEL_POLICY Part B. If usage data is unavailable for a provider, cap by call count and halt that provider at the cap.
- Non-idempotent actions are never retried without checking `external_effect` records.
- Escalations to founder: ≤3/day per role, except security halts.

## §Stop and resume
- **Emergency stop:** dashboard button, `aiorgctl stop`, or `sudo systemctl stop aiorg-worker build-runner`. Halts new work within 5 s; running CLI processes get SIGTERM, then SIGKILL after 30 s; state marked `cancelled` with reason.
- **Builder:** state is git + `TASKS.md` + `HANDOFF.md`; restart the runner and it resumes at the next eligible slice.
- **Organization:** reconciliation on start (ARCH §Recovery). Halt affected tasks on security violations, missing permission, runaway usage, or unrecoverable failure; continue unrelated work; alert the founder with the exact decision needed.
- **Credential revocation:** SETUP §Emergency lists how to sign out each CLI and revoke each key.

## §Deployment
Target is the private staging stack on the Lenovo, reachable only over Tailscale. There is no separate production in v2. Anything public-facing needs a new founder decision.
