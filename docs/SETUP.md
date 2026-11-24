# Founder Setup (v2.1: Claude does most of it)
Never paste API keys, passwords, tokens or private keys into Markdown, chat, or a Claude prompt. Put them in the protected files below and give Claude Code only the variable names.

**How it splits.** You do the steps in **Part A** that need your hands (accounts, sign-ins, keys, one `sudo` command). About 45 minutes, most of it in web consoles. **Part B** is done by Claude Code in a watched bootstrap session: it checks the machine, sets up rootless Docker, verifies the sign-ins and keys, initializes git and pushes, and writes `docs/state/bootstrap.md` listing anything you still owe. **Part C** is the exact prompts to type. Your open decisions are gates in `docs/state/FOUNDER_GATES.md`; each one stops only the slice that needs it.

## Part A. Your hands (do these in order)
### A1. Get the repo onto the Lenovo and run the root script (about 15 minutes, mostly waiting)
- [ ] **H1. SSH works by key** for your admin user. The script reports (never changes) the sshd settings. If it says password login is still on, turn it off yourself, *keeping your current session open* until a new key login works: `sudo sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config && sudo sshd -t && sudo systemctl reload ssh`.
- [ ] **H2.** Copy the zip over and run the one root step. Read the script first; it says at the top what it does and doesn't do.
  ```
  scp ai-org-repo.zip <admin>@<lenovo>:~      # from your Mac
  ssh <admin>@<lenovo>
  unzip ai-org-repo.zip && sudo bash ai-org-repo/scripts/bootstrap/root-setup.sh
  ```
  It installs updates, git, Node LTS, Docker (rootless-ready, nobody in the docker group), Tailscale (not logged in), creates users `aiorg` and `aiorg-coder`, the `/srv/aiorg` folders and empty secret templates (0600 root), copies your SSH key to `aiorg`, makes a GitHub deploy key, copies the repo to `/home/aiorg/ai-org`, installs Claude Code, uv with Python 3.12 (as `aiorg`; Ubuntu 26.10 has no `python3.12` package) and the Codex CLI, and adds a narrow sudoers rule so `aiorg` can start/stop/restart only the AI Org services and reboot (D-036). It ends by printing your next steps.
  **Repo already on the server** (no zip): from the repo folder run `sudo bash scripts/bootstrap/root-setup.sh --refresh-repo`. Run it in a normal SSH terminal (sudo needs to ask for your password; Claude's `!` commands can't). If the folder is a git worktree, the copy's `.git` pointer file is dropped and bootstrap starts a fresh repo for `aiorg`; your history stays in your own repo. Fill the two key files first and you skip the separate `--check-secrets` run: the script always refreshes the key status at the end. If `/home/aiorg/ai-org` exists from an earlier run, it is moved aside (kept, not deleted) and replaced with this copy; without the flag an existing copy is left alone and the script warns.
- [ ] **H3. Tailscale:** `sudo tailscale up`, open the URL and approve. Install Tailscale on your Mac and iPhone and sign in to the same tailnet.

### A2. Accounts and keys (about 25 minutes in web consoles; see PROVIDERS.md for what each is for)
- [ ] **H4. GitHub:** create an **empty private repo** (no README). Settings → Deploy keys → add the public key the script printed (also at `/home/aiorg/.ssh/id_ed25519_github.pub`), **allow write access**. Note the SSH URL for Claude.
- [ ] **H5. Gemini:** create a free API key in Google AI Studio (personal Google account) → `GEMINI_API_KEY`.
- [ ] **H6. OpenRouter** (optional, recommended second free pool): create a key → `OPENROUTER_API_KEY`. Buying ~$10 once raises free-model limits from 50 to 1,000 requests/day; your call.
- [ ] **H7. Anthropic API (approved, $30/month):** create a key in the Anthropic Console, **set the workspace spend limit to $30/month there** → `ANTHROPIC_API_KEY`. Never export it in the `aiorg` shell (bootstrap checks this).
- [ ] **H8. Notion:** Settings → Integrations → new internal integration with read/insert/update content and comment capabilities. Create a database called **AI Org Inbox** and connect the integration to *only that database*. Copy the token → `NOTION_TOKEN` and the database ID (from its URL) → `NOTION_INBOX_DB_ID`. Turn on mobile push for mentions in the Notion app. S05 creates the database properties and checks that a mention reaches your phone.
- [ ] **H9. ntfy** (optional, critical alerts only): app + long random topic + access token → `NTFY_URL`, `NTFY_TOPIC`, `NTFY_TOKEN`.
- [ ] **H10. Put the keys in place** (on the Lenovo, as your admin user):
  ```
  sudo nano /srv/aiorg/secrets/providers.env
  sudo nano /srv/aiorg/secrets/notify.env
  sudo bash /home/aiorg/ai-org/scripts/bootstrap/root-setup.sh --check-secrets
  ```
  The last line writes SET/EMPTY per variable (never values) to `/srv/aiorg/artifacts/secrets-status.txt`, which is all Claude ever sees.

### A3. Sign in the two CLIs as `aiorg` (about 5 minutes)
- [ ] **H11.** From your Mac: `ssh aiorg@<lenovo>` (log in directly, not via `sudo su`, so rootless Docker gets a proper user session). Then `cd ~/ai-org && claude`, choose your Claude subscription login (Max, D-029), open the URL, paste the code back. Type `/status` to see the plan, then `/exit`.
- [ ] **H12.** `codex login --device-auth` (if that flag isn't listed, `codex login --help`), sign in with ChatGPT. Then `chmod 600 ~/.codex/auth.json`.

## Part B. What Claude does in the bootstrap session
Defined step by step in `docs/BOOTSTRAP.md`. In short: checks you're `aiorg` and the API key isn't in the shell; machine checks (OS, CPU/RAM/disk, clock, DNS, Tailscale, ports); toolchain versions; **sets up rootless Docker** and runs `hello-world`; confirms `claude -p` and `codex exec` work; reads the secret status file; configures git, scans for secrets, makes the first commit, verifies GitHub's host key and **pushes to your repo**; lists your open gates; offers to **interview you to draft the Constitution and career targets**; writes `docs/state/bootstrap.md` and updates `HANDOFF.md`. It never uses `sudo`, never reads the secrets folder, and doesn't install plugins (S00 does, under gate G1). Anything it can't do lands on a short "Needs Anwar" list with the exact command.

Then **S00** (also watched) does the rest of the old setup: provider checks against PROVIDERS.md, repo scaffold, plugin and skill install (§3, per G1), the full `.claude/settings.json` allowlist, and the build runner.

## 3. Claude Code plugins and skills (installed by S00; your only part is gate G1)
**Rules.** Install per project (the repo's `.claude/skills/` and project-scoped plugins), not globally, so only this stack's skills are loaded (each one costs about 100 tokens of context per session until it's used). Pin every skill to a commit and record it in `skills/registry.yaml` with its source and the date. Before installing anything that isn't from Anthropic, S00 reads its `SKILL.md` and `scripts/` folder and runs Sentry's `skill-scanner` on it. Skills marked **Runs code** ship hooks, scripts, a binary or a CLI the agent will execute; under D-016 they need your explicit OK (one "yes to the list" is enough): answer gate **G1** in `docs/state/FOUNDER_GATES.md`. Unanswered, S00 installs only the items that don't run code and reports the rest as skipped.

**How S00 installs them (no slash commands needed):** `claude plugin marketplace add anthropics/claude-plugins-official`, then `claude plugin install <name>@claude-plugins-official --scope project` per item (S00 confirms the exact syntax with `claude plugin --help`); stack skills are copied into `.claude/skills/` at a pinned commit.

Sources: Anthropic items were checked against Anthropic's marketplaces on 2026-11-18 and 2026-11-20. Third-party items come from the DEV "Claude Code Skills Directory" (2026-10-15), which says each link was checked on GitHub; S00 confirms each folder still exists before pinning it.

### 3a. Core plugins (Anthropic official marketplace: `/plugin marketplace add anthropics/claude-plugins-official`)
| ID | Install | Why for this project | Used in | Runs code? |
|---|---|---|---|---|
| K1 | `frontend-design@claude-plugins-official` | Sets a deliberate visual direction instead of the template look | S01 and every UI slice | No |
| K2 | `code-review@claude-plugins-official` | Several parallel review agents. **Now on every T1 and T2 slice** (quality-first; on Max the window cost is acceptable), alongside the Codex review | All T1/T2 slices | No |
| K3 | `pr-review-toolkit@claude-plugins-official` | Specialist reviewers (silent failures, test coverage, type design, error handling). Matches what goes wrong in a supervisor, gateway or sandbox | T2 slices: S03, S04, S08, S09, S13 | No |
| K4 | `feature-dev@claude-plugins-official` | Its `code-explorer` and `code-architect` agents produce the written T2 plan. **Use the agents, not the `/feature-dev` command**: the command stops to ask you questions, which would stall the unattended runner | T2 planning: S03, S04, S08, S09, S13 | No |
| K5 | `claude-md-management@claude-plugins-official` | Keeps CLAUDE.md and HANDOFF.md short across 15 fresh sessions | Every slice end | No |
| K6 | `context7@claude-plugins-official` | Current docs for React 19, Vite, React Flow, TanStack, FastAPI, SQLAlchemy, Procrastinate (React Flow has no dedicated skill, so this covers it). Queries go to a third-party service: public library questions only | All slices | **Yes** (MCP server) |
| K7 | `security-guidance@claude-plugins-official` | Warns on injection, XSS and secret patterns as files are edited | All slices | **Yes** (hooks) |
| K8 | `pyright-lsp@claude-plugins-official` | Live Python type information while editing; complements mypy | All backend slices | **Yes** (pyright binary) |

### 3b. Stack skills (copied into `.claude/skills/`, pinned)
| ID | Skill | Source | Why for this project | Used in | Runs code? |
|---|---|---|---|---|---|
| K9 | `react-best-practices` | vercel-labs/agent-skills (official, Vercel) | Stops dated React habits (needless `useEffect`, re-render traps) | All UI slices | No |
| K10 | `web-design-guidelines` | vercel-labs/agent-skills (official) | Pre-ship UI and accessibility review; part of the UI quality gate | UI slices, at slice end | No |
| K11 | `shadcn` | shadcn-ui/ui (official, shadcn) | Adds, composes and fixes shadcn/ui components correctly, including chat UIs | S01, S02, S07, all UI slices | Uses the shadcn CLI (already a dev dependency) |
| K12 | `vitest` | antfu/skills (community, Anthony Fu of the Vite/Vitest core team) | Component tests, mocking, coverage | UI slices | No |
| K13 | `review-animations`, `animation-performance` | emilkowalski/skills (community; the directory rates it the best-written repo) | The org chart's live motion (pulsing cards, travelling message dots) should feel crafted and stay smooth on a phone | S01, S02, S08 | Check in S00 |
| K14 | `webapp-testing` | anthropics/skills (official) | Playwright checks of the running app, screenshots, browser logs; every "What you'll see" test | S01 onward | **Yes** (Python helper scripts) |
| K15 | `supabase-postgres-best-practices` | supabase/agent-skills (official, Supabase; written for any Postgres) | Loads before creating or altering tables: types, indexes, constraints | Every slice with a migration | No |
| K16 | `async-python-patterns`, `python-testing-patterns` | wshobson/agents `python-development` (community; take these two only, not the 90-plugin catalog) | Async FastAPI/worker code and pytest fixtures done properly | All backend slices | No |
| K17 | `docker-build-strategies`, `docker-compose-patterns`, `docker-destructive-guardrails` | docker/skills (official, Docker) | Multi-stage image (Node build stage → slim Python runtime), Compose wiring, and a guard before any command that could wipe volumes | S01, S04, S13 | Check in S00 |
| K18 | `systematic-debugging`, `verification-before-completion` (+ `test-driven-development` for T2) | obra/superpowers (community, in Anthropic's marketplace listing). **Copy these skill folders only, not the plugin**: the full plugin adds a SessionStart hook and brainstorming skills that stop to ask you questions | Any failing test or repair round; before every `SLICE_DONE` | No (as copied) |
| K19 | `differential-review`, `supply-chain-risk-auditor` | trailofbits/skills (Trail of Bits, security firm) | Security review of risky diffs; dependency risk before adding packages | S03, S08, S09, S13 (differential); S00, S12, S13 (supply chain) | No |
| K20 | `skill-scanner`, `find-bugs` | getsentry/skills (official, Sentry engineering) | Scans every non-Anthropic skill before install; a "before merge" bug sweep | S00 and S12 (scanner); T1/T2 slice end (find-bugs) | Check in S00 |

### 3c. Skills for the running organization (loaded into specific roles' `claude -p` calls in later slices)
| ID | Skill | Source | Role | Slice | Runs code? |
|---|---|---|---|---|---|
| K21 | `internal-comms` | anthropics/skills | Chief of Staff: briefing, status and meeting-minute formats | S05, S11 | No |
| K22 | `skill-creator` | anthropics/skills | Skills Librarian, only when no existing skill fits | S12 | **Yes** (eval scripts) |

### Considered and left out
`next-dev-loop` and the other Next.js skills (no Next.js here); `ui-ux-pro-max` (heavy, overlaps K1/K10); `modern-python` (moves the project to uv/ty, which would replace the fixed mypy type checker; revisit only if you want uv); `fastapi-expert` (community, thinner than context7 plus K16); TanStack community skills (context7 covers them); the full `superpowers` plugin, `ralph-loop`, "Everything Claude Code" and other large bundles (they bring their own loops and memory, which fight the runner and the tiers); auth, payment, mobile and Next.js skills (not in this stack).

**What changed from the earlier list (2026-11-20):** `code-review` now runs on every T1/T2 slice, not only T2. `feature-dev` is used for T2 planning through its agents. Parts of `superpowers` are in. Both reversals follow your quality-first direction, and both stay out of T0 work so small tasks don't get extra loops.

## 4. Fill in two short documents (about 20 minutes, the most valuable part; gate G4)
Templates are already in the repo at `constitution/founder.md` and `config/career.yaml`. Edit them yourself, or let Claude interview you in bootstrap step B9 and draft them for your approval. The Constitution is needed before S05. Career targets are needed only when you add the Career project (backlog P2, D-038).
### §Constitution: `constitution/founder.md` (≤4,000 tokens; agents read it on every call, so be specific about your taste and standards)
```
## Who I am
<role, background, what I work on (e.g. agentic AI solutions for business problems)>
## What I'm building and why
<the org's purpose for me: income, career, staying current, time>
## My principles
- State-of-the-art methods (context engineering, prompt engineering, proper planning)
- Efficiency: cheap models for routine work, capable models for judgment
- Quality bar: <tests pass, front-end standards, …>
- Minimal involvement: bring me curated results and real decisions only
## How I like things
<tone of reports, length, what to never do>
## Current priorities (update monthly)
1. … 2. … 3. …
```
### §Career targets: `config/career.yaml`
*Not needed for the build (D-038); fill it in when you add the Career project.*
Target companies (e.g. NVIDIA, Qualcomm, …), role titles, seniority, locations/remote, must-haves, deal-breakers, and the path to your resume on the server (stays `founder_private`).

## 5. Budget and limits
- [ ] Accept or change the default envelopes in MODEL_POLICY Part B (gate **G3**, needed by S03).
- [x] Decided 2026-11-18: CLI runtime accepted (D-026); paid API capped at $30/month (D-027, D-033).

## 6. Backups and emergency
- [ ] Backup destination (external disk, NAS, or encrypted cloud bucket) and retention (gate **G7**, needed by S13).
- [ ] §Emergency, keep this list handy: stop everything `sudo systemctl stop aiorg-worker build-runner && docker compose down`; sign out `claude` (`/logout`) and `codex logout`; revoke Gemini/OpenRouter/API keys in their consoles; remove the deploy key in GitHub (repo Settings → Deploy keys); `sudo tailscale logout` if the machine is compromised.


## Part C. The prompts to type
**1. Bootstrap** (after Part A; you watch it, about 20 minutes). As `aiorg` in `~/ai-org`:
```
claude --model sonnet --permission-mode acceptEdits
```
then type:
> /bootstrap

(Same thing in words, if the command isn't picked up: *"Read CLAUDE.md and docs/BOOTSTRAP.md only. Run the bootstrap. Don't use sudo, don't read the secrets folder, don't answer any founder gate for me. End with the Needs Anwar list, my open gates and the S00 prompt."*)

Fix anything on its Needs-Anwar list, then answer the gates in `docs/state/FOUNDER_GATES.md` (or tell Claude your answers and it records them). G1 matters first; the rest only block later slices.

**2. S00** (fresh session, you watch it): `/exit`, then `claude --model sonnet --permission-mode acceptEdits` again, and type:
> Read CLAUDE.md, then docs/state/bootstrap.md, docs/state/FOUNDER_GATES.md (G1 only), docs/SETUP.md and the S00 section of docs/TASKS.md only. Run S00. Don't read other docs unless S00 lists them. Stop at the end of S00 and show me the preflight report.

**3. S01** (fresh session, you watch it): *"Run slice S01 per CLAUDE.md."* When the org chart shows in your browser over Tailscale, start the hands-free build: `sudo systemctl start build-runner` (or the exact command S00 printed). From S02 on, the runner works through the slices by itself and only stops at a founder gate or a real blocker, posting to your Notion inbox.

## Ready-to-run gate (bootstrap and S00 check all of these)
Access verified · CLIs signed in · free keys present (S00: working) · permissions scoped · envelopes set (G3, by S03) · repo initialized and pushed · emergency stop known · backup path set (G7, by S13). Missing items are recorded as blockers, not skipped.
