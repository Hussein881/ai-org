# What Changed from v1, and Open Questions

## v2.3 scope: organization first, projects later (2026-11-24, founder, D-038)
- No project pipelines in the build. S05 is Constitution + status briefing + alerts (AI news moved to backlog P1). S06 Career moved to backlog P2 (`[-]`). S12 builds a general department/project registration flow; Consulting moved to backlog P3.
- Org chart starts with core roles only: Founder, Chief of Staff, CEO, Board Advisor, Engineering Director + coding workers, QA, Efficiency Assurance. S09 Engineering stays.
- New TASKS marker `[-]` (deferred, skipped by the runner, not mandatory). S07 and S10 test examples no longer use jobs or news. G4 needs only the Constitution; G5 waits for P2.

## v2.2 setup fixes (2026-11-24, after a pre-run review)
- Bootstrap secret scan no longer matches its own pattern (it always failed); B6 reads dir/file modes from the status file.
- **D-036:** runner, worker and key check are system units as `User=aiorg`; scrubbed env for every `claude`/`codex` launch; `scripts/check-env-clean.sh` (names only) runs in bootstrap B1, at the start of every session (CLAUDE.md step 0) and in the runner; narrow sudoers rule (installed by `root-setup.sh`) for those units and the S04 reboot test. `.claude/settings.json` replaces the blanket sudo deny with exact `sudo -n systemctl …` allows, and denies `env`/`printenv`.
- **D-037:** Python 3.12 via uv. `root-setup.sh --refresh-repo` replaces a stale `/home/aiorg/ai-org` (old copy kept).
- Review fallback while K20 isn't approved: Codex + `/code-review` + `reviewer` subagent, marked partial (G1).
- Fixed inconsistencies: runner effort for sonnet is high; stop/start commands are `sudo systemctl …` everywhere; in-slice model escalation happens inside the session; runner resumes a `[~]` slice after reboot; CLI providers in S03 get a scrubbed env.
- Removed duplicate `SETUP_new.md`, the stale worktree and the `ai-org-repo/` copy; merged `.gitignore`.
- First-run fixes (2026-11-24): `root-setup.sh` runs `aiorg` commands from `/home/aiorg` (uv failed reading the admin's home and aborted the script before Python, sudoers and Codex); drops a copied worktree `.git` pointer; always refreshes `secrets-status.txt` at the end. BOOTSTRAP: `--check-secrets` path is `/home/aiorg/ai-org/...` (the admin has no `~/ai-org`); `uv python install 3.12` is pre-approved (already allowed in settings.json).

## v2.1 packaging (2026-11-24): set up by Claude, files in their final places
No change to the design, models, tiers or safety gates. What changed:
- **Layout:** the package is now a ready repo. `CLAUDE.md` at the root, docs in `docs/`, state in `docs/state/`, subagents and commands in `.claude/` (S00 no longer copies them).
- **SETUP.md rewritten** into Part A (your hands: one `sudo` script, accounts, keys, two sign-ins), Part B (what Claude does) and Part C (the exact prompts). Sections §3 to §6 are unchanged apart from gate references.
- **New `scripts/bootstrap/root-setup.sh`:** the only root step. Installs packages, users, folders, secret templates, a GitHub deploy key, Claude Code and Codex. Never edits sshd, logs in, or stores keys.
- **New `docs/BOOTSTRAP.md` and `/bootstrap` command:** a watched first session where Claude, as `aiorg` and without sudo, checks everything, sets up rootless Docker, makes the first commit and push, and lists what you still owe.
- **New `docs/state/FOUNDER_GATES.md`:** your open decisions as gates G1 to G7 (D-034 skills, Docker fallback, envelopes, Constitution/career, P-3, P-4a/b, backups). Slices carry a `Founder gate:` line and stop with `NEEDS_FOUNDER` only if their gate is still unanswered. Nothing was decided for you.
- **New `.claude/settings.json`** with a bootstrap allowlist (denies sudo, force-push and reading the secrets folder); S00 extends it.
- **Templates** for `constitution/founder.md` and `config/career.yaml`; `.gitignore`.
- `CLAUDE.md`: a "First run" pointer, the gate rule, and "no sudo: escalate root steps" (3 lines).

Date: 2026-11-18. v2 keeps v1's safety gates, independent QA, evidence-only reporting and restart safety.

## Your six requirements, and where each one is met
| Requirement | Where |
|---|---|
| 1. Phased vertical slices, small slice 1 | TASKS.md: 5 phases, 15 slices. S01 is only Compose + login + a static org chart. |
| 2. Walking skeleton with UI, visible function each phase, org hierarchy dashboard | Every slice has a "What you'll see" line. ARCHITECTURE §UI: live org chart (status rings, animated message lines, escalations flash red, fuel gauges). |
| 3. Skills to install beforehand | SETUP §3: frontend-design, context7, security-guidance (official marketplace), webapp-testing (anthropics/skills). Also lists what *not* to install and why. |
| 4. Specific model per task | MODEL_POLICY Part A (per slice) and Part B (per runtime role), with the current Claude models: Haiku 5.5, Sonnet 5.5, Opus 5.5, Fable 5.2 for escalation only. |
| 5. No overkill loops | CLAUDE.md §Process tiers: Trivial has no plan or review, Standard has one review at slice end, only High-risk gets the full loop. |
| 6. Context engineering | CLAUDE.md §Context rules, the build runner (a fresh session per slice), `HANDOFF.md` as the only carried state, haiku subagents for search and test output, a `CONTINUE` checkpoint before auto-compaction, and runtime context packs (ARCHITECTURE §Memory). |

## Per-file changes
- **README.md**: rewritten. Adds a one-paragraph picture of the end product, the read order with who reads what, the hands-free build sequence, and a smaller first instruction (S00 only).
- **PROJECT.md**: adds the founder outcomes table (briefing, alerts, jobs, networking, consulting, meetings). New principles: corrections are policy, chain of command with direct QA escalation, need-to-know context with the right to ask, Constitution memory, reuse before building, weekly lessons learned. Adds the model-selection rule at charter level (as you agreed in the conversation). Efficiency Assurance and Career, Research and Consulting are now real departments, not "future".
- **PROVIDERS.md (new)**: what each subscription and free tier can actually do on the server, with sources. Key findings: Claude subscription sign-in can't be used with the Agent SDK. Codex docs steer automation to API keys. Gemini's free tier is real but small and trains on your data. Grok has no free API. GitHub Models was retired in July 2026. Adds the data-routing rule and quota handling.
- **ARCHITECTURE.md**: replaces the two vendor Agent SDKs with an in-house model gateway (CLIs, free APIs, optional paid API). Fixes the stack (Procrastinate, React dashboard (since 2026-11-20), Notion inbox for notifications) so slices don't re-decide it. Adds the Constitution and context packs, chain-of-command matrix, org channel and founder chat, briefing and alerts, pipelines, corrections → policy, weekly meeting, skill sourcing, coder isolation and the org-chart UI. The worker moves to a host systemd service.
- **MODEL_POLICY.md**: rewritten. A model for every slice and every runtime role, escalation rules, quota envelopes, Codex as the cross-vendor reviewer.
- **TASKS.md**: re-sliced. Order changes: the durable worker moves from S08 to **S04**, and useful outcomes (S05 to S07) come right after it, ahead of governance (S08 to S12). Each slice has a tier, model, reviewer, `Read:` list, acceptance and "What you'll see". Adds the build-runner spec, which fixes v1's bootstrap gap: hands-free starts after S01, not S08. The per-slice checklist is replaced by the tiers.
- **CLAUDE.md**: shortened, because it loads every session. Adds the session start routine, the tiers, context rules, the review command, the slice record and the exit statuses the runner reads. Removes "read all docs first".
- **AUTONOMY.md**: split into builder and organization rules. Adds: any paid API use needs you, nothing is sent on your behalf, CEO "major" changes need you, escalation rate limits, usage-window exhaustion is a pause and not a failure, and an emergency stop. Removes the production deployment path (staging on the Lenovo only).
- **VALIDATION.md**: QA by tier. Reviewer identity is recorded (cross-vendor or same-vendor). Adds cross-cutting checks for chain of command, data routing and founder-correction policy.
- **SETUP.md**: rewritten as a checklist. Adds service users, Tailscale, rootless Docker, CLI sign-in on the server, free keys, the Notion integration, plugins and skills, the Constitution and career-targets templates, and an emergency revocation list.
- **DECISIONS.md**: D-002, D-003, D-007, D-010, D-011, D-014 and D-016 are revised. Adds D-018 to D-027 from your answers, plus technical choices T-001 to T-007. D-026 to D-030 record your 2026-11-18 answers.
- **FINAL_REPORT.md**: adds a "what you can use today" section, reviewer identity, and quota/window efficiency next to cost.
- **docs-state/HANDOFF.md (new)**: the state file template carried between fresh sessions.
- **dot-claude/ (new)**: the `explorer` and `test-runner` subagents (Haiku), the fallback `reviewer` (Opus) and the `/review-slice` command. Copy them to `.claude/` in the repo.

## Where files go in the repo
`CLAUDE.md` goes at the repo root. All other `.md` files go in `docs/`. `docs-state/HANDOFF.md` goes to `docs/state/HANDOFF.md`. `dot-claude/*` goes to `.claude/*`. S00 does this copy if you drop the package into `docs/`.

## Founder answers, 2026-11-18 (all folded into the files)
| Question | Answer | Where it landed |
|---|---|---|
| Q1. Run agents on subscriptions via the vendors' CLIs (gray area)? | Yes | DECISIONS D-026, PROVIDERS |
| Q2. Paid Anthropic API fallback? | Yes, capped at $10/month (raised to $30 on 2026-11-20) | D-027, MODEL_POLICY Part B, SETUP §2, AUTONOMY |
| Q3. Plans? | Claude Pro, ChatGPT Plus; **revised 2026-11-20: plan on Claude Max** | D-029, MODEL_POLICY "Claude Max sizing" |
| Q4. Alerts? | Most go to Notion | D-028, ARCHITECTURE §Briefing and alerts, SETUP §2, TASKS S05 |
| Q5. Pause after Phase C? | No | D-030, TASKS |

## Assumptions to confirm
- "Most alerts to Notion" is read as: briefings, alerts, decision requests, meeting minutes and build milestones all go to one Notion database, and only critical items (security halt, everything exhausted) may also push through ntfy, which is optional.
- S00 checks whether Fable is available on your Max tier in Claude Code. If it isn't, Opus at the highest effort is the escalation model.

You'll also fill in the Constitution and career targets (SETUP §4) before S05. They aren't needed to start.

## Revision 2026-11-20: React dashboard and quality audit
You asked whether the plan is so conservative that it hurts product quality. **In several places, yes.** The build process (tiers, review, safety gates) is not where quality is lost. The losses come from runtime model choices, which were driven by Claude Pro plus a $10 cap, and from a lean UI stack. Below is every tradeoff I found, what it costs in quality, and what I did about it.

### Applied now (inside what you've already approved)
| # | Where | What the plan did | Quality cost | Change |
|---|---|---|---|---|
| A-1 | Dashboard (ARCH §Stack, §UI; T-003; S01, S02) | Server-rendered HTMX, hand-drawn SVG org chart | A weaker interactive org chart and chat, and more hand-rolled UI code | **React 19 + TypeScript + Vite**, shadcn/ui, React Flow org chart (custom nodes, animated edges, auto-layout, zoom, minimap), TanStack Query fed by SSE. Built in a Docker build stage, so no Node at runtime. |
| A-2 | News and job triage (MODEL_POLICY Part B, PROVIDERS) | Gemini/OpenRouter free tiers first | Triage decides what reaches you. Free tiers are weaker, capped at about 20 requests a day, and train on the data. | **Haiku 5.5 via the API first** (about $0.01 a day at this volume, well inside the API cap). Free tiers become fallbacks. |
| A-3 | Prompt budgets (ARCH §Memory, §Gateway) | Constitution ≤1,500 tokens, role card ≤600, hard caps | Thin context means more drift and generic output | Constitution ≤4,000 (it's cached, so nearly free), role cards ≤1,500 with worked examples, generous per-role caps tuned down only with evidence, never silent truncation. |
| A-4 | Build effort (MODEL_POLICY Part A) | Sonnet at medium effort for Standard slices | Shallower implementation and more repair rounds | **High effort.** This costs usage-window time, not money. |
| A-5 | UI finish (CLAUDE.md, VALIDATION) | "Smallest implementation" with a smoke test only | Pages that work but feel unfinished | **UI quality gate**: screenshots in desktop/phone and light/dark that the reviewer looks at, axe accessibility, loading/empty/error states, no console errors, design tokens only. |
| A-6 | Review depth on risky slices (SETUP §3, CLAUDE.md) | `code-review` plugin excluded | One reviewer misses more than several | `code-review` **added for High-risk slices only**, on top of Codex. `feature-dev` and `superpowers` still excluded, since they'd add loops to every small task. |
| A-7 | Parallelism (ARCH §Topology, AUTONOMY) | One agent process at a time | Departments queue behind each other, which works against your "run in parallel" goal | **Two concurrent agent processes** from S04, with a free-RAM guard. Three if S13 measurements allow. |

### Proposed for your decision
**P-1. Budget for quality-critical runtime roles. APPROVED 2026-11-20: $30/month, applied (D-033).** Directors (who break work down), career matching, and chat replies run on Haiku, and the Board Advisor only gets Opus when the Pro window allows. Weak decomposition spreads to everything below it, and career matching is one of your core outcomes. *Recommendation:* raise the API cap to **$30 a month**, the top of the $10 to $30 range you mentioned in the original conversation. With that, move Directors, Career matching and chat to **Sonnet 5.5**, and guarantee the **Board Advisor runs Opus 5.5** through the API whenever the CLI window is short. Estimated spend is $20 to $28 a month, and Efficiency Assurance reports actuals weekly.

**P-2. Claude Max. APPROVED 2026-11-20: plan on Max; the build uses each 5-hour window fully, then waits and resumes (D-029). Applied.** On Pro, Opus is scarce, so it only plans the risky core. Max would let Opus implement High-risk slices end to end and speed the build up about 3 to 5 times. You could drop back to Pro afterwards. *Recommendation:* worth it if you want the system in about 2 weeks instead of 6 to 8. It isn't required for correctness.

**P-3. LinkedIn job alerts by email.** The plan only reads official company job boards, because scraping LinkedIn breaks its terms. That misses many postings. *Recommendation:* turn on LinkedIn job alerts sent to a dedicated mailbox, and let Career Intelligence parse the emails you already receive. That is legitimate and far more complete. Adds about half a slice of work to S06.

**P-4. Two-way Notion and semantic memory.** Notion is a one-way mirror today, so you have to open the dashboard to approve anything. *Recommendation:* add Approve/Reject properties that the worker polls, so you can act from Notion, in S10. Separately, add `pgvector` semantic retrieval for lessons and corrections in S11, because keyword search misses rephrased lessons. Both are small.

**Not changed, on purpose:** the safety gates, the three process tiers, the 8 GB host (S13 measures it, and nothing in the plan needs more RAM), and official-source-only scraping.

## Revision 2026-11-20 (later): skills for the stack
SETUP §3 now lists 22 plugins and skills chosen for React + Vite + shadcn/ui + React Flow, FastAPI, Postgres/Procrastinate and Docker, grouped as core plugins, stack skills, and skills for the running organization. Each TASKS.md slice has a `Skills:` line naming the ones it uses, and CLAUDE.md and VALIDATION.md say when the review and debugging skills run. Reversals in your quality-first direction: `code-review` runs on every Standard and High-risk slice; `feature-dev`'s agents write the High-risk plans; `systematic-debugging` and `verification-before-completion` from `superpowers` are in. Trivial tasks still get none of these. **Needs your OK (D-034):** the items marked "Runs code" (context7, security-guidance, pyright-lsp, webapp-testing, skill-creator) plus three to check in S00 (Emil Kowalski's animation skills, Docker's skills, Sentry's skills). Nothing has been installed.
