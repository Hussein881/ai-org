# Vertical Slices: Build Queue
Version 2.1. Markers: `[ ]` pending · `[~]` in progress · `[x]` verified with independent review · `[!]` blocked · `[?]` needs founder · `[-]` deferred to the Project backlog (the runner skips it; not mandatory for completion; D-038).
Rules: one fresh Claude Code session per slice (the runner starts it). Read only this slice's section plus its `Read:` list. Tiers and loops are defined in CLAUDE.md. Every slice ends with something visible in the dashboard.

| Phase | Slices | Milestone you'll notice |
|---|---|---|
| A. See it | S00 to S02 | The org chart is live in your browser; build goes hands-free |
| B. Runs by itself | S03 to S04 | Org survives reboot; real models answer; fuel gauges show quota |
| C. Organization basics | S05, S07 | Constitution, status briefing and alerts in Notion; you can chat with the org |
| D. Governs itself | S08 to S12 | CEO/Board debate, chain of command, coding+QA, corrections → policy, weekly meeting, skills, and the flow you use to add departments and projects |
| E. Hardened and audited | S13 to S14 | Backups, private access, final evidence report |

---
## Phase A: See it

### S00: Preflight and build runner `[x]`
Tier T1, **human-watched (interactive)** · Model `sonnet` · Review: founder reads the preflight report · Depends: bootstrap done (`docs/state/bootstrap.md`, see docs/BOOTSTRAP.md)
Founder gate: G1 (partial rule: install only items that don't run code if unanswered)
Read: `docs/state/bootstrap.md`, `docs/SETUP.md`, `docs/PROVIDERS.md §What S00 must verify`, `docs/AUTONOMY.md`
Skills: K5 K6 K7 K8 K19 (supply-chain) K20 (scanner). Installs and pins K1 to K22 after your OK  (IDs in SETUP §3)
- [ ] Machine checks (reuse `docs/state/bootstrap.md`; re-check only what it marked FAIL or NEEDS ANWAR) (OS, CPU/RAM/disk, clock, DNS, Tailscale up, Docker/rootless status, Python 3.12 (uv), git, sudoers rule (`sudo -n -l`), env clean (`scripts/check-env-clean.sh`), ports, backup path, secret-file permissions). No secret values printed.
- [ ] Provider checks from PROVIDERS.md; record model IDs, plan, limits, and any terms change. Live key checks go through the one-shot `aiorg-keycheck.service` (below): `sudo -n systemctl start aiorg-keycheck.service`, then read `/srv/aiorg/artifacts/keycheck.txt` (PASS/FAIL per provider, never values). Until the founder installs the unit, mark those rows UNKNOWN, not FAIL. Write `docs/state/preflight.md`.
- [ ] Repo scaffold: layout from ARCH §Repo layout (empty packages), `pyproject.toml`, ruff/mypy/pytest config, `.gitignore` (secrets, artifacts, `.env*`), pre-commit with a secret scanner (e.g. gitleaks).
- [ ] Install the plugins and skills from SETUP §3 that gate G1 allows (project scope, pinned commits, `skills/registry.yaml` with provenance); read `SKILL.md` and `scripts/` and run `skill-scanner` on every non-Anthropic skill first; skip and report any that fail or that you haven't approved.
- [ ] `.claude/agents` and `.claude/commands` are already in place (v2.1 packaging); extend the bootstrap `.claude/settings.json` into the full allowlist (edit within repo; `Bash` for `pytest`, `ruff`, `mypy`, `uv`, `npm`/`npx` (incl. `npx playwright`), `git` (no push --force), `docker compose`, `alembic`, `curl localhost`, `codex exec --sandbox read-only`, `systemctl status`/`is-active`, the exact `sudo -n systemctl` lines already there); deny everything else. Keep the `env`/`printenv` denies.
- [ ] Write `scripts/build-runner.sh`, `scripts/ops/keycheck.sh` and three **system** units in `scripts/ops/systemd/` (D-036), then print **one** sudo command for the founder that installs them (founder runs it while watching S00):
  - `build-runner.service`: `User=aiorg`, `EnvironmentFile=/srv/aiorg/secrets/notify.env` **only**, `ExecStart=/usr/local/lib/aiorg/build-runner.sh` (root-owned copy, so a slice can't edit its own supervisor; S00 records that changing the runner means the founder re-installs it), `Environment=XDG_RUNTIME_DIR=/run/user/<aiorg uid> DOCKER_HOST=unix:///run/user/<aiorg uid>/docker.sock`, `After=network-online.target user@<uid>.service`, `Restart=on-failure`, `WantedBy=multi-user.target`, logs via `StandardOutput=append:/srv/aiorg/artifacts/logs/build-runner.log`. Enabled, not started.
  - `aiorg-worker.service`: same shape, `EnvironmentFile=` both env files, `ExecStart=/home/aiorg/ai-org/scripts/run-worker.sh` (a stub that logs "not implemented" and exits 0 until S04 replaces it). Enabled now so S04 needs no root step.
  - `aiorg-keycheck.service`: `Type=oneshot`, `User=aiorg`, both env files, `ExecStart=/usr/local/lib/aiorg/keycheck.sh` (root-owned copy): one minimal authenticated request per provider, writes `provider: PASS|FAIL <http status>` to `/srv/aiorg/artifacts/keycheck.txt`, never values or response bodies.
  - The sudo command: `install -o root -g root -m 0755` the two scripts to `/usr/local/lib/aiorg/`, `install -m 0644` the units to `/etc/systemd/system/`, `mkdir -p /srv/aiorg/artifacts/logs` (owned by aiorg), `systemctl daemon-reload`, `systemctl enable build-runner.service aiorg-worker.service`. Nothing else.
  Dry-run the runner on a no-op slice.
- [ ] Update `docs/state/HANDOFF.md` (bootstrap already initialized it).
**Acceptance:** preflight report with every check PASS/FAIL/UNKNOWN; runner dry-run moves a dummy slice `[ ]→[x]` and back; with a planted fake key variable in the runner's environment the runner refuses to launch `claude` and marks the slice `[!]` (test); keycheck rows PASS or UNKNOWN (unit not yet installed); no secrets in git (scanner passes). Missing prerequisites are marked `[!]` with the exact fix.
**What you'll see:** `docs/state/preflight.md` in the repo, and `systemctl status build-runner` (stopped until you start it after S01).
**Gate:** no hands-free running until you've read the preflight report.
**Closed 2026-11-24 by founder override (option C):** merged with Codex review FAIL x4; `scripts/build-runner.sh` is NOT approved for hands-free use (open defects in docs/state/slices/S00.md). Run S01 by hand; finish and re-review the runner before `systemctl start build-runner`.

### S01: Walking skeleton with org chart `[x]` (review partial, see slice record)
Tier T1, **human-watched** · Model `sonnet` (effort high), `frontend-design` skill for the visual direction · Review `codex` · Depends S00
Founder gate: G2, only if `docs/state/bootstrap.md` shows rootless Docker FAIL
Read: ARCH §Topology §Stack §UI §Security
Skills: K1 K9 K10 K11 K12 K13 K14 K15 K16 K17 · review K2 K20 (find-bugs) · finish K18  (IDs in SETUP §3)
- [ ] Docker Compose: `postgres`, `api` (multi-stage image: Node stage runs `vite build`, runtime stage is Python + the static `dist/`), health checks, volumes, memory limits. Alembic baseline migration with `roles`, `role_versions`, `events`, `users`.
- [ ] Founder login (single account, argon2, secure cookie, CSRF); bind to Tailscale IP.
- [ ] React app scaffold in `web/` (Vite, TypeScript strict, Tailwind, shadcn/ui init, TanStack Router/Query, ESLint, Vitest), OpenAPI → TS type generation wired into the build.
- [ ] Seed roles from `roles/*.yaml` (the PROJECT.md org). **Org chart page** with React Flow: custom role-card nodes (name, model badge, status ring, all "idle" for now), ELK auto-layout, zoom/pan/minimap; click → shadcn drawer with the role card.
- [ ] Visual direction via the `frontend-design` skill: Tailwind theme tokens, light and dark mode; responsive list view for phones.
- [ ] Playwright smoke: login → org chart renders all roles → drawer opens.
**Acceptance:** `docker compose up --build` clean on the Lenovo (build time and peak RAM recorded); health green; unauthenticated request denied; smoke passes on desktop and phone viewport; UI quality gate passes (VALIDATION §UI quality gate); idle RAM recorded.
**What you'll see:** open `http://<lenovo-tailscale-name>:8000`, log in, see your company's org chart.
**Then:** you run `sudo systemctl start build-runner`. From here the build is hands-free.

### S02: Tasks, events and live status `[x]` (review partial, see slice record)
Tier T1 · Model `sonnet` · Review `codex` · Depends S01
Read: ARCH §Data model §State machine §UI
Skills: K9 K10 K11 K12 K13 K14 K15 K16 · review K2 K20 · finish K18  (IDs in SETUP §3)
- [ ] Tables: `projects, tasks, runs, events, audit_log`. State machine with validated transitions (incl. `awaiting_info`).
- [ ] Task intake form ("Assign to CEO"), task board page, task detail with event timeline.
- [ ] **SSE stream** feeding TanStack Query: org chart status rings, animated React Flow edges and an activity ticker update live.
- [ ] A fake "echo" worker loop (in-process, no LLM) that picks up a task, sets the CEO card to *working*, emits events, and completes it. Proves the end-to-end loop visually.
**Acceptance:** submitted task keeps ID/status across browser refresh and `docker compose restart`; invalid transition rejected; SSE reconnects after api restart.
**What you'll see:** submit a task and watch the CEO card pulse, the ticker scroll, and the task move across the board.

**Phase A milestone:** tag `phase-a-done`; runner posts a milestone page to the Notion inbox (or just logs, if Notion isn't configured yet).

---
## Phase B: Runs by itself

### S03: Model gateway, usage ledger, fuel gauges `[!]` (blocked with S04; see slice record)
Tier **T2** · Plan `opus` (written), implement `sonnet` · Review `codex` + adversarial tests · Depends S02
Founder gate: G3
Read: ARCH §Gateway §Security, `docs/PROVIDERS.md` (all), `docs/MODEL_POLICY.md Part B`
Skills: plan K4 · K15 K16 · review K2 K3 K19 (differential) · finish K18 (incl. TDD)  (IDs in SETUP §3)
- [ ] Gateway interface, router, fallback chain, `data_class` enforcement, redaction, prompt-assembly order.
- [ ] CLI providers (`claude_cli`, `codex_cli`) run in a scrubbed environment like the build runner's (`env -i` allowlist), since the worker holds the API keys: otherwise `claude -p` bills the API and the CLIs can see keys. Test: a planted fake key variable never reaches a CLI subprocess.
- [ ] Providers: `fake`, `claude_cli`, `codex_cli`, `anthropic_api` (enabled within the $30 cap), `gemini_api`, `openrouter_free`; `openai_api` present but disabled by policy.
- [ ] `model_usage` + `provider_quota` ledger, envelopes from MODEL_POLICY, reset-time tracking, 429 handling (queue until reset).
- [ ] Top-bar **fuel gauges**; role drawer shows model + calls today.
- [ ] Replace the echo worker's reply with one real `claude_cli haiku` call (a one-line CEO acknowledgement), behind a feature flag.
**Acceptance:** `founder_private` request routed to a free tier is refused (test); exhausted envelope falls back then queues (test with fake clock); redaction removes a planted fake secret from prompt and logs; ledger never fabricates tokens (NULL when unknown); one live smoke call per enabled provider recorded.
**What you'll see:** gauges for Claude (subscription and API spend), Codex, Gemini, OpenRouter; the CEO replies to your task in real words.

### S04: Durable worker and restart safety `[!]` (escalation repair failed Codex verification; founder decision)
Tier **T2** · Model `opus` · Review `codex` + crash tests · Depends S03
Read: ARCH §Recovery §State machine §Stack, `docs/AUTONOMY.md §Stop and resume`
Skills: plan K4 · K15 K16 K17 · review K2 K3 K19 · finish K18 (incl. TDD)  (IDs in SETUP §3)
- [ ] Procrastinate worker behind the `aiorg-worker.service` system unit S00 installed (host, `User=aiorg`; replace the `scripts/run-worker.sh` stub; control it with the `sudo -n systemctl … aiorg-worker.service` lines), running up to 2 agent processes concurrently with a free-RAM guard; job locks, retries with backoff, dead-letter, idempotency keys, `external_effect` records, heartbeats/leases, periodic-task scheduler.
- [ ] Restart reconciliation for abandoned runs. Emergency stop (`/admin/stop` + `aiorgctl stop`) that halts new work within 5 s.
- [ ] Dashboard: worker heartbeat indicator, dead-letter list, "stop everything" button (confirm dialog).
**Acceptance:** kill -9 worker mid-run → task resumes once, no duplicate effect; reboot test → services return, queue intact, nothing falsely `completed`; emergency stop verified.
**Reboot test procedure (sudoers rule D-036):** commit, write in HANDOFF "S04 reboot test pending: verify after boot" and what to check, add `"Bash(sudo -n systemctl reboot)"` to the allowlist on the slice branch, then run it. The session dies with the machine; `build-runner` (enabled) comes back and resumes S04 (`[~]`) in a fresh session, which verifies and removes that allow entry again. Interactive tmux sessions do not survive the reboot.
**What you'll see:** a green "worker alive" dot; reboot the laptop and watch everything come back.

**Phase B milestone (hands-free runtime):** tag `phase-b-done`; Notion milestone page.

---
## Phase C: Organization basics (right after hands-free)

### S05: Constitution, Chief of Staff status briefing, alerts `[ ]`
Tier T1 · Model `sonnet` · Review `codex` · Depends S04
Founder gate: G4 (Constitution)
Read: ARCH §Memory §Briefing and alerts §Gateway, SETUP §2 (Notion)
Skills: K9 K11 K14 K15 K16 K21 · review K2 K20 · finish K18  (IDs in SETUP §3)
- [ ] `constitution/founder.md` v1 drafted **from the template in SETUP §Constitution** (founder fills it); versioned in DB; injected in every gateway prompt prefix; editable on a Settings page with version history.
- [ ] Chief of Staff **morning status briefing** (scheduled 06:30, configurable): overnight events and exceptions, task progress, blocked work, quota/spend status, decisions needed. Briefing page with history. Sections come from a small **briefing-section registry**, so a project added later (S12 flow, Project backlog) plugs in its own section without changing the briefing code. No news, jobs or other project content in this slice (D-038).
- [ ] Alerts and delivery (ARCH §Briefing and alerts): `alerts` + `outbox` tables; Notion **AI Org Inbox** mirror (create properties, write pages, @-mention founder on action items, retry on failure); optional ntfy for `critical`; quiet hours; dashboard bell.
- [ ] Deterministic QA for briefing: every item links to its evidence record (event, task, ledger row), no duplicates, times within the window.
**Acceptance:** a briefing is generated by the scheduler (not by hand) on two consecutive mornings; a test alert appears in the Notion inbox and the mention notifies the phone (if mentions via the API don't notify, record it and enable ntfy for action items); a Notion outage doesn't block the briefing; every item links to evidence; a fixture section registered in a test appears in the briefing; `founder_private` content never hits a free-tier provider (ledger check).
**What you'll see:** a status briefing page in Notion at 06:30, and the Chief of Staff card lighting up on the org chart when it's written.

### S06: (moved to the Project backlog) `[-]`
Career intelligence is a project, added after the organization is formed (D-038). See **Project backlog: P2** at the end of this file. Nothing depends on S06.

### S07: Chat with the organization `[ ]`
Tier T1 · Model `sonnet` · Review `codex` · Depends S05
Read: ARCH §Channels and chat §Memory
Skills: K9 K11 K12 K14 K16 · review K2 K20 · finish K18  (IDs in SETUP §3)
- [ ] Chat panel on every page; default recipient Chief of Staff; `@CEO` routing. Conversation persisted.
- [ ] Grounded answers through read tools over DB (tasks, briefings, events, quota); "create task", "approve", "correct this" intents (correct just records for now; S10 makes it policy).
- [ ] Haiku for quick replies, Sonnet when the ask needs synthesis.
**Acceptance:** "what happened overnight?" answer cites real events; "ask Engineering to look at X" creates a task visible on the board; no answer invents a task or number (tested with fakes).
**What you'll see:** you talk to your company from your phone.

**Phase C milestone:** tag `phase-c-done`; Notion milestone page. The runner continues straight into Phase D (founder decision D-030).

---
## Phase D: Governs itself

### S08: CEO planning, chain of command, Board Advisor, approvals `[ ]`
Tier **T2** · Plan `opus`, implement `sonnet` · Review `codex` + adversarial tests · Depends S07
Read: ARCH §Chain of command §Governance §Channels and chat, PROJECT §Operating principles 1 to 6
Skills: plan K4 · K9 K11 K13 K15 K16 · review K2 K3 K19 · finish K18 (incl. TDD)  (IDs in SETUP §3)
- [ ] CEO (codex_cli) turns founder requests into schema-validated plans, task cards, dependencies; classifies risk and major/minor.
- [ ] Board Advisor (claude_cli opus) reviews CEO plans above a risk threshold: agree / prefer-alternative / **strong disagreement → founder decision card + alert**.
- [ ] `comm_matrix` enforcement on all messages; QA/EA/Board direct-to-founder escalation with evidence and rate limits.
- [ ] Approvals queue page; founder approve/reject with reason; denial persists.
- [ ] Org chart animates message edges; escalations flash red.
**Acceptance:** a disallowed message (e.g. worker → founder) is rejected and audited; strong disagreement produces a founder decision; high-risk plan cannot proceed unapproved; malformed CEO output rejected.
**What you'll see:** CEO and Board debating on your org chart, and a decision card when they truly disagree.

### S09: Engineering pipeline (coding worker + independent QA) `[ ]`
Tier **T2** · Model `opus` · Review `codex` + sandbox-escape tests · Depends S08
Read: ARCH §Isolation §State machine §Recovery, `docs/VALIDATION.md`
Skills: plan K4 · K15 K16 · review K2 K3 K19 · finish K18 (incl. TDD)  (IDs in SETUP §3)
- [ ] Engineering Director dispatches task cards to a coding worker: `claude -p --model sonnet` in a per-task worktree as `aiorg-coder`, explicit allowedTools, turn cap, timeout.
- [ ] QA: codex_cli read-only review + deterministic test run; defects linked; ≤2 repair rounds; completion gate.
- [ ] `awaiting_info`: worker can ask its director a question instead of guessing.
**Acceptance:** seeded trivial feature implemented, tested, committed on a branch; deliberately defective change rejected, repaired, re-verified; worker cannot read `/srv/aiorg/secrets` or another worktree (test); retry exhaustion → `failed_qa`, never `completed`.
**What you'll see:** assign "add a feature to <toy repo>" and watch Engineering → worker → QA on the chart, with the diff and verdict.

### S10: Founder corrections become policy `[ ]`
Tier T1 · Model `sonnet` · Review `codex` · Depends S08
Founder gate: G6a (P-4 Notion approvals; if YES, also read CHANGES.md §P-4)
Read: ARCH §Governance §Memory
Skills: K9 K11 K15 K16 · review K2 K20 · finish K18  (IDs in SETUP §3)
- [ ] Versioned `policies` with diff view and one-click revert.
- [ ] "Correct this" on decisions, classifications, messages, briefing items → Chief of Staff drafts a policy or Constitution diff → applied as new version approved by the correction → founder notified with the diff.
- [ ] Later prompts cite the policy version; CEO major/minor misclassification corrected by founder updates the classification rule.
**Acceptance:** a correction changes the next run's behavior in a test (e.g. "leave quota status out of the briefing unless a provider is above 80%" changes the next briefing); revert restores prior version; agents cannot change governance by themselves.
**What you'll see:** "Correct this" buttons, and a Policies page showing your corrections as versions.

### S11: Weekly lessons-learned meeting `[ ]`
Tier T1 · Model `sonnet` · Review `codex` · Depends S10
Founder gate: G6b (P-4 pgvector; if YES, also read CHANGES.md §P-4 and record the T-006 change in DECISIONS)
Read: ARCH §Governance, MODEL_POLICY Part B
Skills: K9 K11 K16 K21 · review K2 K20 · finish K18  (IDs in SETUP §3)
- [ ] Efficiency Assurance role: weekly metrics from the ledger and events (QA failure rate, repairs, latency, quota use, corrections, escalations).
- [ ] Scheduled meeting (default Sunday 18:00): CEO chairs, Board, QA, EA, directors with items post in `#lessons`; Chief of Staff writes minutes; `lessons` rows; proposals into the approval queue.
- [ ] Meetings page; founder can comment live via chat.
**Acceptance:** a meeting runs from the scheduler with real metrics; at least one lesson is retrieved into a later relevant prompt (test); proposals require founder approval to enact.
**What you'll see:** Sunday-evening minutes and a short list of proposed improvements to approve.

### S12: Skills sourcing and the department/project registration flow `[ ]`
Tier T1 · Model `sonnet` · Review `codex` · Depends S11
Read: ARCH §Governance §Pipelines
Skills: K9 K11 K16 K19 (supply-chain) K20 (scanner) K22 · review K2 · finish K18  (IDs in SETUP §3)
- [ ] Skills registry page (pinned versions, provenance, reviews). Skills Librarian searches approved sources before anyone writes a new skill; install needs founder approval.
- [ ] Department/project registration flow, in the dashboard: proposal (purpose, roles, sources, schedule, briefing section, budget) → founder approval → role cards → policy → org chart node appears. An approved project is registered but **inactive** until its own build slice (Project backlog) ships its pipeline. No real department is added in this slice (D-038); tests use a fixture department.
- [ ] An approved proposal shows a ready-to-paste build slice for it (from its backlog entry, or drafted from the proposal). The app never edits the build repo; the founder adds the slice to TASKS.md, or asks a Claude session to.
**Acceptance:** an unapproved department cannot run; an unapproved skill cannot be loaded; a fixture department appears on the org chart only after approval, and its registered briefing section appears empty until it has output.
**What you'll see:** an "Add department or project" form; after you approve a proposal, its card appears on the org chart.

**Phase D milestone:** tag `phase-d-done`; Notion milestone page.

---
## Phase E: Hardened and audited

### S13: Hardening, backups, private access `[ ]`
Tier **T2** · Model `opus` · Review `codex` + restore test · Depends S12
Founder gate: G7
Read: ARCH §Security §Recovery, `docs/AUTONOMY.md`
Skills: plan K4 · K17 K19 · review K2 K3 K19 · finish K18 (incl. TDD)  (IDs in SETUP §3)
- [ ] Nightly backups to the founder's destination; restore into a clean test stack; retention.
- [ ] Port/firewall review (only SSH + Tailscale); secrets audit (git history, logs, DB); log retention; health monitoring with alerts; performance check on the Lenovo under a normal day's load.
- [ ] Operator runbook and rollback procedure, demonstrated once.
**Acceptance:** restore succeeds; no public listener besides SSH (or none, if SSH is Tailscale-only); full suite passes on the host; rollback demonstrated.
**What you'll see:** a "System health" page and a weekly backup-OK line in the briefing.

### S14: Final end-to-end audit and report `[ ]`
Tier T1 · Model `sonnet`; report cross-checked by `opus` in fresh context · Depends S13
Read: `docs/VALIDATION.md`, `docs/FINAL_REPORT.md`, all `docs/state/slices/*.md` (summaries only)
Skills: K14 · cross-check K2 · finish K18  (IDs in SETUP §3)
- [ ] Full scenario: founder request → CEO plan → Board review → director → worker → QA → Chief of Staff report → briefing. Negative tests: approval denied, quota exhausted, provider outage, worker crash, chain-of-command violation.
- [ ] Generate `FINAL_REPORT.md` from evidence; list open issues and risks.
**Acceptance:** every mandatory criterion verified or the report says PARTIAL/BLOCKED; numbers trace to ledger rows and test logs.
**What you'll see:** the final report, linked from the dashboard.

---
## Build runner (`scripts/build-runner.sh`, written in S00)
Loop: read `docs/TASKS.md` → next `[ ]` slice whose dependencies are `[x]` → parse its header for the model; effort is that model's default in MODEL_POLICY Part A (haiku low, sonnet high, opus high) → in a scrubbed environment (`env -i` with only `HOME PATH USER LOGNAME LANG TERM XDG_RUNTIME_DIR DOCKER_HOST`; the runner's own `NOTION_*`/`NTFY_*` never pass through) first run `scripts/check-env-clean.sh`; if it isn't `ENV_CLEAN`, don't launch, mark the slice `[!]` "key variables in session env" and alert → run
`claude -p "Run slice <ID> per CLAUDE.md." --model <model> --effort <effort> --permission-mode acceptEdits --output-format json` in the repo, with `.claude/settings.json` allowlists in force → read the final status line:
- `SLICE_DONE` → verify the marker is `[x]` and the slice record exists → next slice. At a phase tag, post to the Notion inbox.
- `CONTINUE` → start a fresh session on the same slice (context cleared). Max 4 continuations per slice, then `[!]`.
- `BLOCKED` / `NEEDS_FOUNDER` → Notion inbox item with the reason (mentioning the founder), skip to the next independent slice if any, else stop.
- Usage-limit or rate-limit error (5-hour or weekly window) → the session has already checkpointed (CLAUDE.md asks for small commits, and an interrupted session's work stays on the slice branch); the runner records the reset time from the error message, or probes with a tiny `claude -p --model haiku "ok"` every 20 minutes if no time is given, sleeps until then, and resumes the **same** slice in a fresh session that starts from `HANDOFF.md` and the branch. Not counted as a failure and doesn't use a continuation. A pause expected to last more than 6 hours (weekly limit) posts a Notion inbox item with the expected resume time.
- Any other error → one retry, then `[!]`.
- On start (including after a reboot), a slice already `[~]` is resumed first, in a fresh session from `HANDOFF.md` and its branch (not counted as a continuation).
- Notion posts before S05 (which adds the inbox properties) are title + body only; if Notion fails, log to `/srv/aiorg/artifacts/logs/build-runner.log` and keep going.

State lives only in git, `TASKS.md` markers and `HANDOFF.md`, so a reboot just restarts the loop (the unit is enabled at boot). The runner never edits code itself and never changes models outside the slice header; in-slice escalation (MODEL_POLICY §Escalation rules) happens inside the session through subagent model overrides and is recorded in the slice record.

---
## Project backlog (not built until the founder adds them; D-038)
The organization is built first (S00 to S14 without S06). Each project below is added later: you approve it in the S12 flow, then its build slice is added to the queue. Until then these are notes, not work: the runner never starts them.

### P1: AI and agentic-AI news (AI Research department) `[-]`
From the original S05: source allowlist, fetch, dedup, triage (Haiku API, free tiers as fallback), Sonnet summary of the top items, all with source links; a "News" briefing section; deterministic QA (every item has a resolving URL, no duplicates, dates within window). Read when added: ARCH §Pipelines.

### P2: Career intelligence (Career Intelligence department) `[-]`
Tier T1 · Model `sonnet` · Review `codex` · Depends S12 (registered through the department/project flow)
Founder gate: G4 (career targets) and G5 (P-3; if YES, also read CHANGES.md §P-3 and add the email-alert ingest)
Read: ARCH §Pipelines §Memory §Gateway, SETUP §Career targets
Skills: K9 K11 K14 K15 K16 · review K2 K20 · finish K18  (IDs in SETUP §3)
- [ ] Target list (companies, roles, locations, seniority) from SETUP; official public job-board feeds/APIs only; `jobs_seen` dedup.
- [ ] Public-data parsing on free tier; matching against profile on Claude only; ranked matches with why-it-fits and a link.
- [ ] Networking targets from public sources, with a drafted (not sent) intro note.
- [ ] Briefing sections + Jobs page (save / dismiss; dismissals feed matching).
**Acceptance:** fixture-based tests for parsing and dedup; live run returns ≥1 real posting from a target company or a clear "none found" with sources checked; nothing is submitted or sent anywhere.
**What you'll see:** "Jobs for you" and "People to meet" in the briefing.

### P3: Consulting Intelligence `[-]`
From the original S12: a department with a founder-approved source list; leads go into a "Consulting leads" briefing section.
