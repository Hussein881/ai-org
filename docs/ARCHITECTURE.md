# System Architecture
Version: 2.0 | Status: implementation baseline. Slices cite sections by name (e.g. "ARCH §Gateway"); read only the cited sections.

## §Topology
```
Mac / iPhone ──Tailscale──► Lenovo (Ubuntu Server LTS)
                             ├─ Docker Compose: postgres, api (FastAPI JSON API + SSE, also serves the prebuilt React app)
                             ├─ systemd: aiorg-worker  (task queue worker + model gateway + scheduler)
                             ├─ systemd: build-runner  (only during the build; runs Claude Code per slice)
                             └─ CLIs for user aiorg: claude, codex   (subscription sign-in, protected)
Notifications: Notion (primary: an "AI Org Inbox" database in the founder's workspace, via the Notion API); ntfy push (optional, critical alerts only; see SETUP)
```
Why the worker is on the host, not in a container: it must invoke the signed-in `claude` and `codex` CLIs, whose credentials live in the `aiorg` user's home. Coding workers still run isolated (see §Isolation). Memory budget on 8 GB: Postgres ≤512 MB, api ≤256 MB, worker ≤512 MB plus up to **two** concurrent CLI agent processes from S04 (~0.5 to 1 GB each), raised to three if S13 measurements show ≥1.5 GB free under load. Leave ≥1.5 GB free; the worker refuses to start a new agent process below that.

## §Stack (decided, to avoid per-slice deliberation)
- Python 3.12, FastAPI, SQLAlchemy 2 + Alembic, Pydantic v2, pytest.
- **Queue and scheduler: Procrastinate** (PostgreSQL-backed task queue with locks, retries and periodic tasks). No custom queue. If S04 finds a blocking defect, the fallback is a `SELECT … FOR UPDATE SKIP LOCKED` table with leases, recorded as a decision.
- **UI: React 19 + TypeScript + Vite (founder decision D-031).** The app is built once per release in a Node stage of the `api` Docker image (multi-stage build); the runtime image contains only the static `dist/` files, served by FastAPI. **No Node process runs in production.**
  - Components: **shadcn/ui** (Radix primitives + Tailwind CSS), so dialogs, drawers, tables and forms are accessible by default and look consistent.
  - Org chart: **React Flow** (`@xyflow/react`) with custom role-card nodes, animated edges, minimap, zoom/pan, and automatic layout with ELK (`elkjs`).
  - Data: **TanStack Query** for server state; the SSE stream (`EventSource`) pushes events that update or invalidate the matching queries, so every page is live without polling. Routing: **TanStack Router** (type-safe routes).
  - Charts (fuel gauges, efficiency metrics): shadcn charts (Recharts). Motion: CSS transitions plus Framer Motion only where it earns its weight (card status changes, drawer).
  - API contract: FastAPI's OpenAPI schema → TypeScript types generated with `openapi-typescript` in the build; a CI check fails if the generated types are stale. No hand-written API types.
  - Tests: Vitest + React Testing Library for components; Playwright for end-to-end and screenshots; `@axe-core/playwright` for accessibility.
  - Auth stays a same-origin secure session cookie (no tokens in the browser), with a CSRF header on mutating requests.
- Auth: single founder account, argon2 password hash, secure session cookie, CSRF on forms; dashboard bound to the Tailscale interface only.
- Lint/format/type: ruff, ruff format, mypy (strict on `core/`, `gateway/`, `policy/`).

## §Repo layout
```
app/  core/ (ids, state machine, events, audit)   policy/ (policies, chain of command, approvals)
      gateway/ (providers, router, ledger, redaction)   org/ (roles, agents, memory, meetings)
      pipelines/ (news, careers, consulting)   api/ (FastAPI routers, SSE)   workers/
web/              React app (Vite): src/{routes,components,features,lib}, generated api types, design tokens
roles/            role cards (YAML), versioned
constitution/     founder.md (identity, goals, principles, preferences), versioned
config/           career.yaml (founder_private) and other founder-owned config
skills/           vendored, pinned skills with provenance
docs/             this package + docs/state/ (HANDOFF.md, FOUNDER_GATES.md, bootstrap.md, slices/, preflight.md)
scripts/          build-runner.sh, backup.sh, restore.sh, bootstrap/root-setup.sh
tests/            unit/, integration/, e2e/ (Playwright smoke)
```

## §Data model (minimal; add columns only when a slice needs them)
`users, projects, tasks, task_dependencies, runs, events, audit_log, roles, role_versions, agent_instances, channels, messages, approvals, policies, policy_versions, corrections, constitution_versions, memories, lessons, meetings, model_usage, provider_quota, artifacts, test_results, qa_reviews, briefings, briefing_items, sources, jobs_seen, contacts_suggested, skills, skill_sources, alerts`.
Every row: stable UUID, `created_at`, actor, schema version, `data_class` (public | founder_private | secret-ref), and `project_id/task_id/run_id` where relevant. Events and audit are append-only.

## §State machine
Task: `draft → ready → running → verifying → completed`, plus `blocked, awaiting_approval, awaiting_info, failed_qa, failed_execution, cancelled`. `awaiting_info` is the "come back and ask" state: a worker may raise a question to its manager instead of guessing. Runs are separate from tasks; each retry is a new run. Transitions are transactional and validated; completion requires a QA record (or, for Trivial-tier internal tasks, a deterministic check record).

## §Gateway (model gateway)
One interface for every model call: `complete(role, task_ref, prompt_parts, schema, data_class, budget_hint) -> Result`.
- **Providers:** `fake` (deterministic, used in CI), `claude_cli` (`claude -p --model <alias> --output-format json [--json-schema]`, run with no tools unless the role is a coding worker), `codex_cli` (`codex exec`, read-only sandbox, schema output where supported), `anthropic_api` (enabled within the approved cap; Haiku 5.5 is the default for public-data bulk work), `gemini_api` (free tier) and `openrouter_free` (fallbacks for public data only), `openai_api` (disabled).
- **Router:** role default from `MODEL_POLICY.md §Runtime` → check data_class allowed → check quota envelope → fallback chain → else queue until reset.
- **Ledger:** every call writes `model_usage` (provider, model id, tokens if reported else NULL, latency, outcome, cost if API else 0 with `pricing_basis='subscription'|'free'`). Never invent token counts.
- **Prompt assembly order** (cache-friendly, stable prefix first): Constitution → role card → policy excerpts for the role → task card → retrieved memories → recent failure evidence. Per-role size caps start generous (e.g. 30k tokens for directors, 60k for the Chief of Staff briefing) and are tuned down only when the weekly metrics show no quality loss; a cap is never applied by silently truncating inputs (the gateway summarizes or splits instead, and logs it).
- **Redaction** runs on every outbound prompt and every stored transcript.

## §Memory and context packs (runtime context engineering)
- **Constitution** (`constitution/founder.md`, versioned in DB): who the founder is, what he's building, his principles ("state of the art methods", efficiency, quality bar, front-end taste, minimal involvement), preferences. ≤4,000 tokens (raised from 1,500: it is a cached prefix, so a richer Constitution costs almost nothing per call and reduces drift). Included in every agent's prompt prefix. Only founder edits or founder corrections change it.
- **Role card**: mission, responsibilities, allowed tools, who it may talk to, output schema, escalation triggers, two or three worked examples of good output. ≤1,500 tokens.
- **Task card**: goal, acceptance criteria, inputs, constraints, deadline. Written by the manager; this is the handoff unit between agents.
- **Memories**: `lessons` (from weekly meetings), `corrections` (founder), and per-role notes, retrieved by role and tag (plain SQL + full-text search first; vectors only if evidence shows need).
- Agents never receive raw transcripts of other agents; they get summaries or task cards. No context is given that the task does not need.

## §Chain of command
`policy.comm_matrix` lists allowed (sender_role → recipient_role, purpose) pairs. Default:
Founder↔CEO, Founder↔Chief of Staff, CEO↔Directors, CEO↔Board Advisor, Director↔its workers, Director↔Director (coordination only), Chief of Staff reads all channels (read-only), **QA → Founder (escalation)**, **Efficiency Assurance → Founder (escalation)**, **Board Advisor → Founder (strong disagreement)**.
The message API rejects anything else (`403 chain_of_command`) and audits it. Escalations require `evidence_refs` and are rate-limited (e.g. ≤3/day per role) to prevent alarm spam; repeated low-value escalations are themselves a lessons-learned item.

## §Channels and chat
- **Org channel** (Slack-like): agents post structured messages to project channels and `#org`; every message has sender, recipient(s), parent, task/run refs. Chief of Staff summarizes.
- **Founder chat**: a chat panel on every page. Founder talks to the Chief of Staff by default, or `@CEO`. Messages become tasks, answers, corrections or approvals. Answers are grounded in DB state (tasks, briefings, events) via tools, not guessed.

## §Briefing and alerts
- Daily scheduled job (default 06:30 local) assembles the **morning briefing** since the last briefing: decisions needed, overnight exceptions, task progress, quota status, plus one section per registered department or project (none at first; D-038). Rendered on the dashboard and pushed as a short phone notification with a link.
- **Alerts**: immediate push for QA/EA escalations, Board strong disagreement, approval needed for blocked critical work, quota/budget exhaustion, security halts. **Delivery (founder decision D-028):** every briefing, alert, decision request, meeting minute and build milestone is written as a page in the Notion **AI Org Inbox** database (properties: Type, Severity, Status, Role, Link back to the dashboard record), with the founder @-mentioned on items that need action so Notion notifies his phone. The dashboard bell shows the same items; Postgres stays the source of truth and Notion is a one-way mirror (a failed Notion write is retried from an outbox table and never blocks work). Only `critical` items (security halt, emergency stop, all providers exhausted, Notion unreachable for >1 h) also go to ntfy, if configured. No secrets are ever written to Notion. Quiet hours configurable; critical alerts bypass them.
- Every item links to its source URL or evidence record. No item without a source.

## §Pipelines (departments)
These are projects in the TASKS.md Project backlog, built only after the founder adds them through the S12 flow (D-038). The design below is kept for when they are added.
- **AI Research**: fetch from an allowlist of sources (RSS/Atom, arXiv listings, official vendor blogs/changelogs, Hacker News API) → dedup → free-tier triage → Claude summary for top items.
- **Career Intelligence**: official public job-board APIs/feeds of target companies (e.g. Greenhouse/Lever/Workday public endpoints where terms allow) → parse (free tier, public data) → match against the founder's profile (**founder_private ⇒ Claude/OpenAI only**) → ranked matches with why-it-fits; networking targets from public sources (company engineering blogs, conference speakers, meetups). No logins as the founder, no auto-apply, no auto-messaging: drafts only.
- **Consulting Intelligence** (backlog P3): same pattern, sources approved at the time.

## §Governance
- **Policies** are versioned rows (YAML body). Every change records author, reason, diff, approver. Agents may *propose*; only the founder (or a founder correction) enacts governance changes; CEO may enact changes the policy itself marks `minor`.
- **Corrections → policy**: any decision, classification, message or briefing item has "Correct this". The founder's text plus the target record go to the Chief of Staff, which drafts a policy/constitution diff; the diff applies immediately as a new version with `approved_by=founder (correction #id)`, is shown to the founder, and can be reverted in one click. Later runs cite the policy version they used.
- **Weekly lessons-learned meeting** (S11): scheduled; agenda auto-built from metrics (QA failure rate, retries, latency, quota use, founder corrections, escalations). Participants: CEO (chair), Board Advisor, QA, Efficiency Assurance, directors with items. Output: minutes, `lessons` rows, proposed changes into the approval queue. Founder can join live via chat or just read the summary.
- **Skills registry and sourcing** (S12): before writing a new skill, the requesting director asks the Skills Librarian (a temporary worker) to search approved sources (`anthropics/skills`, `anthropics/claude-plugins-official`, and founder-added sources) and propose a pinned version with provenance and a review. Installing any executable skill needs founder approval.

## §Isolation (coding workers)
Each coding task gets a git worktree under `/srv/aiorg/workspaces/<task_id>`, owned by unprivileged user `aiorg-coder`, which has no access to `/srv/aiorg/secrets`, the Docker socket or other workspaces. `claude -p` is run with an explicit `--allowedTools` list (edit/read in the worktree, `Bash(pytest *)`, `Bash(git *)` limited by a wrapper), a turn cap and a timeout. Network egress for coder processes is limited where practical (documented if not). Code QA runs in a separate process (Codex, read-only).

## §Observability and triage
Backend captures: assignment, prompt metadata (redacted, hashed full prompt stored only if `data_class` allows), tool events, outputs, errors, provider/model, usage, retries, tests, commits, approvals. Correlation ID across gateway calls. Drill-down path: briefing item or alert → task → message → run → gateway call → test → diff → retry.

## §UI (walking skeleton grows each slice)
Home = **Live Org Chart**:
- Cards per role: name, model badge (e.g. "Opus 5.5 · claude_cli"), status ring (idle grey, working blue pulse, waiting-for-info amber, blocked red, awaiting-founder purple), current task title, today's calls.
- Edges animate (a dot travels along the line) when a message passes between roles; escalation lines to the founder flash red.
- Click a card: drawer with role card, current task, recent messages, last outputs, policy version, fuel used.
- Top bar: provider fuel gauges, pending approvals count, alerts bell, "next briefing at 06:30".
Other pages, added by slices: Tasks board, Channels, Briefing, Approvals, Policies (with diff view), Meetings, Runs/Traces, Skills, Settings. Mobile: org chart collapses to a vertical list with the same status rings. Visual direction is set once in S01 with the `frontend-design` skill and kept as Tailwind theme tokens (`web/src/styles/tokens.css`), with dark mode from day one. The org chart is a React Flow canvas: custom nodes for role cards, animated edges for live messages, ELK auto-layout, zoom and minimap, and a keyboard-accessible list view of the same data for screen readers and small phones.

## §Security
Dedicated non-root accounts (`aiorg` service, `aiorg-coder` for workers, your admin user for SSH). Rootless Docker preferred (membership in the `docker` group is root-equivalent; if rootless is impractical, the build user's docker access is a recorded founder-accepted risk). Secrets in `/srv/aiorg/secrets/*.env` (0600, root-owned, injected by systemd `EnvironmentFile` into **system** units that run as `User=aiorg`: `build-runner` gets `notify.env` only, `aiorg-worker` and the one-shot `aiorg-keycheck` get both; D-036), never in Git, Markdown or prompts. Every `claude`/`codex` subprocess (build sessions and runtime CLI providers) starts from a scrubbed environment and is checked with `scripts/check-env-clean.sh`. Residual risk: worker code is written by build sessions and runs with the keys in its environment; the review gates are the control. CLI credential files (`~/.claude`, `~/.codex/auth.json`) 0600. Untrusted content (web pages, job posts, repo text, tool output) is data, never instructions; pipeline prompts wrap it in delimiters and the gateway strips instruction-like content from tool outputs before they reach privileged roles. Dashboard is never exposed publicly.

## §Recovery and integrity
Procrastinate locks + task idempotency keys; runs record side effects (`external_effect` rows) before and after; on restart, reconcile `running` runs: if no heartbeat within lease, mark `abandoned`, check recorded side effects, then retry or escalate. No blind re-execution of non-idempotent actions. Nightly `pg_dump` + artifacts tarball to the backup destination; restore tested in S13.

## §Deferred choices
Vector store (see proposal P-4 in CHANGES.md), OpenTelemetry/Langfuse, LangGraph, n8n, multi-provider dynamic routing. Each needs a measured reason and a decision record.
