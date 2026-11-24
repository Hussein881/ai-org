# Model Policy: Who Builds What, Who Runs What
Version 2.0. Objective: lowest **total cost per verified outcome** (tokens, subscription-window minutes, retries and your time), not lowest price per token. The cheaper model is the default wherever it is capable; stronger models are used where judgment or risk justifies them, or after evidence of failure.

## Part A: Building the system (Claude Code on the server)
Claude Code model aliases resolve to the latest model of each family. Current mapping (Nov 2026; S00 confirms which your plan allows):

| Alias | Model | Role in the build | Default effort |
|---|---|---|---|
| `haiku` | Claude Haiku 5.5 | Trivial-tier slices and tasks; the `explorer` and `test-runner` subagents | low |
| `sonnet` | Claude Sonnet 5.5 | **Default implementer** for Standard-tier slices | **high** (raised from medium: costs usage-window time, not money) |
| `opus` | Claude Opus 5.5 | Planner and implementer for High-risk slices; Claude-side reviewer when Codex is unavailable | high |
| `fable` | Claude Fable 5.2 | **Escalation only**: after 2 failed repair rounds on a High-risk slice, or an architecture deadlock. No slice is planned on it. S00 checks whether your Max tier offers it in Claude Code; if not, escalation is `opus` at `xhigh`, then blocked. | high |
| Codex (ChatGPT plan default) | Recorded at S00 | **Independent cross-vendor reviewer** (read-only) for Standard and High-risk slices | default |

Why a different vendor reviews: a reviewer from another model family shares fewer blind spots with the implementer, and it spends your ChatGPT subscription instead of your Claude window.

**Claude Max sizing (D-029, revised 2026-11-20).** Plan on Claude Max. The build is allowed to use up each 5-hour window completely; the runner then waits for the reset and resumes on its own (see TASKS §Build runner). So: (a) `opus` implements the High-risk slices end to end (S04, S09, S13) and writes the plans for S03 and S08; nothing is downgraded to save the window; (b) S00 records whether `fable` is available in Claude Code on your Max tier; if it is, it is the escalation model, otherwise `opus` at `xhigh`; (c) the weekly limit can also run out; the runner waits for that reset too and tells you in Notion when a pause will be longer than 6 hours; (d) your own interactive Claude use shares the same windows, so stop the runner (`sudo systemctl stop build-runner`) if you need Claude yourself and start it again afterwards. Expect about 3 to 5 slices a day, so roughly 1 to 2 weeks for all 15 slices, plus any weekly-limit pauses.

### Per-slice assignment (authoritative copy lives in each TASKS.md slice header, which also lists the skills each slice uses; skill IDs are in SETUP §3)
| Slice | Tier | Implement | Plan | Review |
|---|---|---|---|---|
| S00 Preflight + build runner | Standard (human-watched) | sonnet | inline | founder watches |
| S01 Walking skeleton + React app + org chart | Standard | sonnet (+ frontend-design skill) | inline | codex + UI quality gate |
| S02 Tasks, events, live status | Standard | sonnet | inline | codex |
| S03 Model gateway + fuel gauges | High-risk (credentials, data routing) | opus plans, sonnet implements | written (feature-dev agents) | codex + adversarial tests |
| S04 Durable worker + restart safety | High-risk (concurrency, idempotency) | opus | written | codex + `code-review` plugin + crash tests |
| S05 Constitution, status briefing, alerts | Standard | sonnet | inline | codex |
| S06 (deferred to Project backlog P2, D-038) | n/a | n/a | n/a | n/a |
| S07 Founder chat | Standard | sonnet | inline | codex |
| S08 CEO, chain of command, Board Advisor, approvals | High-risk (authority) | opus plans, sonnet implements | written | codex + adversarial tests |
| S09 Engineering pipeline (coding worker + QA) | High-risk (sandbox) | opus | written | codex + `code-review` plugin + escape tests |
| S10 Corrections → policy | Standard | sonnet | inline | codex |
| S11 Weekly lessons-learned meeting | Standard | sonnet | inline | codex |
| S12 Skills sourcing + department/project registration flow | Standard | sonnet | inline | codex |
| S13 Hardening, backups, private access | High-risk (security) | opus | written | codex + `code-review` plugin + restore test |
| S14 Final audit + report | Standard | sonnet | inline | opus (fresh context) cross-checks report vs evidence |

Inside any slice, small sub-tasks (docs, config, fixtures, renames, copy text) are delegated to a `haiku` subagent rather than done by the slice's main model.

### Escalation rules (build)
1. A Standard slice that fails review twice → re-plan once on `opus`, implement on `sonnet`.
2. A High-risk slice that fails twice on `opus` → one attempt on `fable` (if available), then **blocked** with evidence.
3. Never retry the same model on the same failure with the same context a third time.
4. Rate-limit or usage-window errors are **not** failures: the runner waits for reset; no model change.

## Part B: Running the organization (runtime defaults)
Routes are provider names from `PROVIDERS.md`. `→` is the fallback chain. The CLI routes are founder-approved (D-026). `anthropic_api` is enabled with a hard $30/month cap (D-027, D-033); `openai_api` stays disabled.

| Role | Primary | Fallbacks | Why | Est. calls/day |
|---|---|---|---|---|
| CEO | codex_cli (ChatGPT plan default model) | claude_cli `opus` → openai_api | Capable planner; different vendor from the Board Advisor so the challenge is real | 3 to 8 |
| Board Advisor | claude_cli `opus` (Opus 5.5) | anthropic_api `claude-opus-5-5` (**guaranteed**: used whenever the CLI window can't serve Opus) | Founder decision: Claude is the co-advisor | 1 to 4 |
| Chief of Staff (briefing, summaries) | claude_cli `sonnet` (Sonnet 5.5) | anthropic_api `claude-sonnet-5-5` | Writes what you read; quality matters | 3 to 6 |
| Chief of Staff (chat replies) | anthropic_api `claude-sonnet-5-5` | claude_cli `sonnet`; Haiku 5.5 only for intent routing | You talk to it directly, so it gets the stronger model (D-033) | 0 to 20 |
| Directors (decompose, route) | anthropic_api `claude-sonnet-5-5` | claude_cli `sonnet` | Decomposition quality flows into everything below it (D-033) | 5 to 15 |
| News / job scouts (public data; only once backlog P1/P2 are added, D-038) | anthropic_api `claude-haiku-5-5` | gemini_api free → openrouter_free | Triage decides what reaches you, so it needs a reliable model. Haiku 5.5 costs $0.10/$0.50 per M tokens: ~100 articles a day is about $0.01/day, so free tiers save almost nothing while adding weaker triage, ~20 req/day limits and data-training terms | 20 to 60 |
| Career matching (uses your profile; only once backlog P2 is added) | anthropic_api `claude-sonnet-5-5` | claude_cli `sonnet` | Core outcome; `founder_private` data: no free tiers (D-033) | 2 to 5 |
| Coding worker | claude_cli `sonnet` | claude_cli `opus` on escalation | Best value for coding | on demand |
| QA (code) | codex_cli read-only | claude_cli `opus` in fresh context | Cross-vendor independence | on demand |
| QA (non-code outputs) | deterministic checks first (links resolve, dates, dedup, schema) | claude_cli `haiku` | Cheapest reliable check | 2 to 5 |
| Efficiency Assurance | SQL metrics (no model) + claude_cli `haiku` narrative | `sonnet` for weekly report | Numbers come from the ledger, not the model | 1 |
| Skills Librarian (temporary) | claude_cli `haiku` | `sonnet` | Search and summarize candidates | weekly |

Default envelope (founder-tunable in policy): sized for Claude Max and ChatGPT Plus: **during the build**, the build runner has priority and the organization's `claude_cli` use pauses whenever the runner is active; **after the build**, `claude_cli` ≤80 calls/day and ≤20 per 5-hour window, of which Opus ≤20/day; `codex_cli` ≤12/day; `anthropic_api` ≤$30/month hard cap with a $1.00/day soft limit (expected $20 to $28/month); heavy jobs scheduled 01:00 to 06:00. When the CLI window is tight, routine Claude roles (directors, chat quick replies, QA narrative) prefer `anthropic_api` Haiku 5.5 when the CLI window is above 70% used, since those calls cost fractions of a cent and protect the window for Opus and Sonnet work. If `opus` is unavailable through the CLI, the Board Advisor runs on `sonnet` via CLI or `claude-opus-5-5` via the API within the cap. These numbers are starting guesses; Efficiency Assurance adjusts them with evidence via the weekly meeting.

## Context discipline (both parts)
Pass only: Constitution (runtime) or CLAUDE.md (build), the role/slice card, the policy or architecture sections cited, minimal code excerpts, and recent failure evidence. Stable content first for caching. Summaries, never transcripts. Targeted tests during a slice; the full suite only at phase milestones.

## Measurement
Per call/run: provider, model ID, tokens if reported (else NULL, shown as UNKNOWN), latency, attempts, pricing basis (`subscription`, `free`, `api` with price source and date), pass/fail, review outcome. Weekly: verified success rate, repairs, latency and quota use per role and task category. Never invent figures.

## Governance
No automatic limit increases. New providers, new paid usage, or moving a role's default model is a policy change: CEO may propose with evidence; founder approves. Benchmark a candidate on 10 representative tasks before switching a default.
