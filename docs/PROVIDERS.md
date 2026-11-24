# Providers: What Your Subscriptions and Free Tiers Can Actually Do
Researched 2026-11-18. Terms and limits change often; S00 re-verifies every row and records the result in `docs/state/preflight.md`. Where a source is a third-party summary rather than the vendor, that is noted.

## The short answer
- **The build** (Claude Code writing this system on the server) is fully covered by your Claude subscription. That is exactly what the subscription is for. The only constraint is your plan's usage limits, which the build runner handles by pausing and resuming.
- **The running organization** is the hard part. Consumer subscriptions are licensed for *you* using the vendor's own apps. Anthropic's terms say subscription OAuth is meant only for Claude Code and Claude.ai, and that using those tokens in any other product, **including the Claude Agent SDK**, is not permitted ([The Register, 2026-02-20](https://www.theregister.com/2026/02/20/anthropic_clarifies_ban_third_party_claude_access/)). OpenAI's Codex docs recommend API keys, not ChatGPT sign-in, for automated/CI use ([Codex auth docs](https://learn.chatgpt.com/docs/auth)).
- So v2 drops v1's plan to run agents on the **OpenAI Agents SDK and Claude Agent SDK** (both need paid API keys). Instead, a small in-house **model gateway** calls the vendors' *own CLIs* (`claude -p`, `codex exec`) for low-volume judgment work, real **free APIs** for high-volume public-data work, and an **optional paid API key** as fallback.
- Calling the vendors' own CLIs headlessly from your own server for your own personal use is the most defensible subscription route, but **unattended automation is a gray area** in both vendors' terms and can trigger usage reviews. v2 keeps that volume low (a few dozen calls a day), never resells or shares access, and makes the API fallback a one-line config switch. **You accepted this risk on 2026-11-18 (D-026)**, with the capped paid fallback (D-027) as the safety net. If either vendor tightens its terms or flags the account, the gateway switches those roles to the API with a one-line policy change.

## Provider table
| Provider / route | Use in build | Use in org runtime | Status | Limits and risks |
|---|---|---|---|---|
| **Claude subscription via Claude Code** (`claude` interactive, `claude -p` headless) | **Primary builder.** All slices. | CEO-level judgment, Board Advisor, Chief of Staff briefing, coding workers. Low volume. | Build: clearly allowed. Runtime: gray area (headless Claude Code is documented; automated use under consumer terms is not explicitly blessed). | Shared 5-hour and weekly usage windows with your own interactive use. Your plan is **Max**: the build uses each 5-hour window fully and resumes after reset; Opus is available; S00 checks Fable. Policy can tighten without notice. |
| **ChatGPT subscription via Codex CLI** (`codex exec`, sign in with ChatGPT; device-code sign-in exists for SSH/headless) | **Independent cross-vendor reviewer** for Standard and High-risk slices. | CEO planning (cross-vendor with the Claude Board Advisor), code QA. Low volume. | Interactive: allowed. Automated: docs steer automation to API keys; gray area. | ChatGPT **Plus** usage limits (smaller than Pro; envelope ≤12 calls/day); `~/.codex/auth.json` holds tokens and must be protected like a password. |
| **Gemini API free tier** (Google AI Studio key) | Not used. | Bulk public-data work: news triage, dedup, job-post parsing, classification. | Allowed: it is a real API tier. | Google no longer publishes free-tier numbers; third-party measurements report as low as ~20 requests/day on the newest Flash model ([memetik.ai, 2026-10](https://www.memetik.ai/guides/gemini-api-free-tier-limits), [aiplug.work](https://aiplug.work/en/blog/gemini-free-tier-limits)). **Free-tier content is used to improve Google's products**, so only public data may go there. |
| **OpenRouter `:free` models** | Not used. | Second free pool for the same public-data jobs; failover when Gemini quota is exhausted. | Allowed. | 20 req/min; 50 req/day, or 1,000 req/day after a one-time purchase of about $10 in credits ([kingy.ai, verified 2026-10-19](https://kingy.ai/ai-limits/ai-limits-openrouter/)). Free models can log prompts: public data only. |
| **Grok (xAI)** | Not used. | Not used by default. | **No free API tier** as of Nov 2026; the $150/month data-sharing credit ended May 2025; a SuperGrok/X subscription does not include API access ([aifreeapi.com, 2026-11-14](https://www.aifreeapi.com/en/posts/xai-grok-api-pricing), third-party). | Pay-as-you-go only (cheapest text model ~$1.25/$2.50 per M tokens, third-party figure). Can be added later as a paid provider with founder approval. |
| **GitHub Copilot** | Not used. | Not used by default. | **GitHub Models (the free inference API) was retired on 2026-07-30** ([GitHub docs](https://docs.github.com/en/github-models/use-github-models/prototyping-with-ai-models)). Copilot's own CLI is for interactive use under your subscription. | Revisit only if you want Copilot as an extra interactive coding tool. |
| **IBM Bob** | Not used. | Not used. | An IDE product; no documented headless API for a server. | S00 checks for a CLI/API; if none, it stays out. |
| **Anthropic API key (paid)** | Not needed. | Primary for Directors, career matching, chat and public-data triage (D-032, D-033); fallback for other Claude roles. | Clearly allowed. **Approved, $30/month cap (D-027, D-033).** Set the same limit in the Anthropic Console so it is enforced by the vendor too. | Claude Haiku 5.5 is $0.10/$0.50 per M input/output tokens; Sonnet 5.5 $2/$10; Opus 5.5 $4/$20. A daily briefing on Haiku is a few cents a day. At the cap, the gateway disables the provider until next month and tells you. |
| **OpenAI API key (paid, optional fallback)** | Not needed. | Fallback for the CEO role. | Clearly allowed. Needs approval. | Record model IDs and prices at S00. |

## Data-routing rule (enforced by the gateway, not by prompts)
Every gateway call carries a `data_class`:
- `public` (news articles, public job posts, public profiles): Haiku 5.5 API first (quality, and it costs about a cent a day at this volume); free tiers are fallbacks.
- `founder_private` (Constitution, resume, preferences, chat, corrections): **Claude or OpenAI routes only** (subscription CLI or paid API), never free tiers that train on or log content.
- `secret`: never sent to any model. Redacted before any call.

## Quota and window management
- The gateway keeps a **usage ledger** per provider: calls, tokens (when reported), errors, 429s, and the reset time of each window.
- Each provider has a **budget envelope** in policy: e.g. `claude_cli: max 25 calls/day, max 6 per 5h window, pause org use 07:00 to 22:00 if founder is actively using Claude` (defaults; founder-tunable). The org never starves your own interactive use.
- On exhaustion: free tier → next free tier → (if approved) paid fallback → otherwise queue until reset and tell the Chief of Staff. Never silently drop work.
- The dashboard shows a **fuel gauge** per provider (used / limit / resets at).

## What S00 must verify (and record without secrets)
1. Which Claude plan is active, which models `claude --model` accepts (`haiku`, `sonnet`, `opus`, `fable`), and that `claude -p --output-format json` works over SSH.
2. `codex login` via device code on the server; `codex exec` works read-only; record the default model ID it reports.
3. Gemini key works; record the free-tier limits shown in AI Studio for the chosen Flash/Flash-Lite model.
4. OpenRouter key works; record `GET /api/v1/key` limits.
5. Whether a paid fallback key is configured and its cap.
6. Re-check the Anthropic and OpenAI terms pages; if either has tightened, mark the CLI runtime route **BLOCKED pending founder** and continue with free tiers + fake providers.
