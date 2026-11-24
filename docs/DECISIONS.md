# Decision Register
Every new decision records: ID, decision, rationale, alternatives, impact, approver, date, linked slice. Status: **A** approved · **P** pending founder · **R** revised from v1 · **S** superseded.

## Founder policy decisions
| ID | Decision | Rationale | Status |
|---|---|---|---|
| D-001 | Ubuntu Server LTS on the existing Lenovo | Low-cost, always-on host | A |
| D-002 | Docker Compose for postgres + api; worker and build runner as systemd services on the host | Simple, inspectable; worker needs signed-in CLIs | R (v1: everything in Compose) |
| D-003 | Cloud inference through an in-house **model gateway** calling vendor CLIs (subscription), free-tier APIs, and optional paid APIs. Vendor Agent SDKs are not used for org agents. | Agent SDKs need paid API keys; subscription OAuth may not be used in the Agent SDK | R (v1: OpenAI Agents SDK + Claude Agent SDK) |
| D-004 | Provider-neutral role and task interfaces | Avoid lock-in | A |
| D-005 | Founder controls policy, authority and major changes | Prevent autonomous privilege escalation | A |
| D-006 | CEO approves routine low-risk plans | Avoid micromanagement | A |
| D-007 | Risk-proportionate process with three tiers (T0/T1/T2) | Avoid overkill loops on small tasks | R (made concrete) |
| D-008 | Bounded automatic retry and delegation | Fewer interruptions without runaway loops | A |
| D-009 | Per-project conversation timeline and traceability | Auditable history | A |
| D-010 | Independent QA before verified completion; cross-vendor (Codex) where possible | Prevent self-certified success | R (cross-vendor added) |
| D-011 | All approved slices proceed automatically via the build runner (fresh session per slice); S00 and S01 human-watched | Hands-free with a working bootstrap | R (fixes v1 bootstrap gap) |
| D-012 | First useful pipeline (news + briefing, then careers, then chat) right after the hands-free milestone, before governance polish | Founder answer 2026-11-18 | **Superseded by D-038** |
| D-013 | Cheaper capable model first; escalate on evidence | Cost per verified outcome | A |
| D-014 | Collect usage from day one; fuel gauges early, analytics UI later | Visibility without scope creep | R |
| D-015 | Dedicated scoped accounts and protected secrets | Security | A |
| D-016 | Versioned roles/skills; controlled additions; **source existing skills before writing** | Reuse, prevent uncontrolled growth | R |
| D-017 | LangGraph and n8n deferred | Avoid redundant orchestration | A |
| D-018 | Board Advisor runs on Claude (Opus 5.5) | Founder answer 2026-11-18 | A (new) |
| D-019 | Build and runtime use existing Claude/ChatGPT subscriptions and free tiers first | Founder answer 2026-11-18 | A; amended by D-032 (public-data triage moved to Haiku 5.5 API because free tiers cost quality for ~1 cent/day of savings) |
| D-020 | Everything, including the Claude Code build, runs on the server over SSH | Founder answer 2026-11-18 | A (new) |
| D-021 | Founder corrections automatically become versioned policy (revertible) | "It should be a policy update because I have the say" | A (new) |
| D-022 | Chain of command enforced in backend; QA, Efficiency Assurance and Board may escalate directly to founder with evidence | Design conversation | A (new) |
| D-023 | Constitution (founder identity/principles) injected into every agent call | Prevent drift over days of running | A (new) |
| D-024 | Weekly lessons-learned meeting (CEO, Board, QA, Efficiency Assurance, directors) | Design conversation | A (new) |
| D-025 | Agents draft outreach and applications; they never send or submit on the founder's behalf | Reputation and terms-of-service risk | P (proposed default) |
| D-026 | Use vendor CLIs headlessly on subscriptions for low-volume runtime judgment calls (gray area, see PROVIDERS.md) | Uses existing subscriptions | A (founder, 2026-11-18; risk accepted) |
| D-027 | Paid Anthropic API, capped at $30/month (raised from $10 on 2026-11-20, D-033) | Reliability if subscriptions/free tiers run out or terms tighten | A (founder, 2026-11-18) |
| D-028 | Most alerts, briefings and decision requests go to Notion (AI Org Inbox database); optional ntfy push for critical alerts only | Founder answer 2026-11-18 | A (new) |
| D-029 | Plans: **Claude Max** (revised 2026-11-20 from Pro) and ChatGPT Plus. The build may use each 5-hour window fully, then waits for the reset and resumes automatically | Founder answers 2026-11-18 and 2026-11-20 | A (revised) |
| D-030 | No pause after Phase C; the runner continues through all phases | Founder answer 2026-11-18 | A (new) |
| D-031 | React dashboard (Vite build at image-build time, no Node at runtime) | Founder request 2026-11-20: a richer, more interactive org chart and chat | A (new) |
| D-032 | Quality-over-thrift adjustments within existing approvals: public-data triage on Haiku 5.5 API instead of free tiers; richer prompt budgets; 2 concurrent agent processes; Sonnet at high effort for Standard slices; UI quality gate; `code-review` plugin on High-risk slices | Founder asked 2026-11-20 where conservatism hurts quality | A (applied; see CHANGES.md) |
| D-033 | Raise the API cap and upgrade quality-critical runtime roles (directors, career matching, chat, Board) | Biggest remaining quality lever | A (founder, 2026-11-20: $30/month) |
| D-034 | Project-scoped skill set K1 to K22 (SETUP §3), pinned with provenance; `code-review` on all T1/T2 slices; `feature-dev` agents for T2 plans; selected `superpowers` skills | Founder asked 2026-11-20 which skills fit the stack, quality-first | A (founder 2026-11-24: G1 YES-ALL; K13, K17, K20 pending S00 scan; until K20, T1 review is Codex + `/code-review` + `reviewer` subagent, marked partial) |
| D-036 | Services and secrets: `build-runner`, `aiorg-worker` and a one-shot `aiorg-keycheck` are **system** units with `User=aiorg`, so key files stay root-only (systemd reads `EnvironmentFile` as root). Runner loads `notify.env` only; every `claude`/`codex` launch uses a scrubbed env (`env -i` allowlist) and `scripts/check-env-clean.sh` fails the launch/slice on any key variable. Runner and keycheck scripts run from root-owned copies in `/usr/local/lib/aiorg/`. A narrow sudoers rule lets `aiorg` start/stop/restart those units and reboot (S04 test only); founder installs units with one sudo command in S00 | The `systemctl --user` plan couldn't read root-only keys (no Notion alerts at gates, no live key checks) and loading keys into the runner would leak them into build sessions and bill the API | A (founder, 2026-11-24) |
| D-037 | Python 3.12 via `uv` for `aiorg` (user space), not apt/deadsnakes | Host runs Ubuntu 26.10 (system Python 3.14, no `python3.12` package); keeps the fixed stack | A (founder, 2026-11-24) |
| D-038 | Build the organization first, projects later: no news, careers or consulting pipelines in the build. S05 becomes Constitution + status briefing + alerts; S06 moves to the Project backlog; S12 builds a general department/project registration flow (tested with a fixture). Core org chart: Founder, Chief of Staff, CEO, Board Advisor, Engineering Director + coding workers, QA, Efficiency Assurance. S09 Engineering stays. | Founder, 2026-11-24 | A (founder, 2026-11-24) |
| D-035 | v2.1 packaging: root-only steps in one founder-run script; everything else done by Claude in a watched `/bootstrap` session as `aiorg` without sudo; open decisions tracked as gates in `docs/state/FOUNDER_GATES.md` | Founder asked 2026-11-24 for a setup Claude can do itself, to build autonomously | Decided (packaging only, no design change) |

## Technical choices (made now to save per-slice deliberation; reversible with a recorded reason)
| ID | Choice | Alternatives considered |
|---|---|---|
| T-001 | FastAPI + SQLAlchemy 2 + Alembic + PostgreSQL | SQLite (weaker concurrency), Django (heavier) |
| T-002 | Procrastinate for queue + periodic tasks | Custom SKIP LOCKED table (fallback), Celery+Redis (extra service, more RAM) |
| T-003 | **React 19 + TypeScript + Vite**, shadcn/ui, React Flow org chart, TanStack Query/Router, SSE; built in a Docker build stage, served as static files by FastAPI (D-031) | Jinja2 + HTMX (v2 draft; leaner but weaker for an interactive org chart and a chat UI), Next.js (needs a Node server at runtime) |
| T-004 | Notion API (internal integration, scoped to one database) as the notification mirror; ntfy optional for critical | Telegram bot, email (SMTP credentials) |
| T-005 | Single-user argon2 login + Tailscale-only binding | OAuth IdP (unneeded for one user) |
| T-006 | Plain SQL + Postgres full-text search for memory retrieval | Vector DB (add only with evidence) |
| T-007 | Rootless Docker preferred | docker group (root-equivalent; needs founder acceptance) |

## Still to be chosen during slices
Exact free-tier model IDs (S00/S03), news source allowlist and job-board endpoints (when backlog P1/P2 are added), backup destination details (S13).
