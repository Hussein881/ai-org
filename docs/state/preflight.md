# Preflight report (S00, 2026-11-24)
No secret values anywhere in this file. Status: PASS / FAIL / UNKNOWN / PENDING.

## Machine (re-used from bootstrap, spot-rechecked)
| Check | Result | Note |
|---|---|---|
| OS, CPU, RAM, disk | PASS | Ubuntu 26.10, 4 CPU, 7.1 GiB RAM (~3.6 GiB available), 68 GB free |
| Clock / DNS / Tailscale | PASS | NTP synchronized; tailscale0 up (anwar-server 100.66.205.39) |
| Docker rootless, Python 3.12 (uv), git, node | PASS | per bootstrap B3/B4 |
| Env clean | PASS | `ENV_CLEAN` |
| Sudoers rule | PASS | `sudo -n -l` lists only the D-036 systemctl start/stop/restart lines, keycheck start, reboot |
| Secret files | PASS | per bootstrap B6 (root 700/600; only names read) |
| Ports | NOTE | Nothing on 80/443/5432/8000. Localhost-only listeners exist on 8080, 8088, 55432 and a few high ports (not ours; check before S01 binds anything). SSH 22 is open on all interfaces. |
| Backup path | PENDING | gate G7 (S13) |
| Git remote | NEEDS ANWAR | no origin yet (bootstrap B7) |

## Providers (PROVIDERS.md §What S00 must verify)
| # | Item | Result | Evidence |
|---|---|---|---|
| 1 | Claude aliases over `claude -p --output-format json` | PASS | haiku=claude-haiku-5-5, sonnet=claude-sonnet-5-5, opus=claude-opus-5-5, fable=claude-fable-5-2 |
| 1 | Claude plan tier | UNKNOWN | not readable non-interactively; founder runs `/status` (D-029 says Max) |
| 2 | Codex | PASS | logged in via ChatGPT; `codex exec --sandbox read-only` works; default model gpt-6.2-sol |
| 3 | Gemini key + free-tier limits | UNKNOWN | key SET; live check waits for `aiorg-keycheck.service`; limits are shown only in AI Studio |
| 4 | OpenRouter key + `/api/v1/key` limits | UNKNOWN | key SET; same |
| 5 | Paid fallback key and cap | PARTIAL | ANTHROPIC_API_KEY SET; $30/month cap is set in the Console (D-027), not verifiable from here; live check UNKNOWN |
| 6 | Anthropic/OpenAI terms re-check | UNKNOWN | no recorded baseline to compare against and no terms-page fetch was done; nothing observed that suggests a change (both CLIs work). Founder: confirm you want this checked, then it is a web-fetch step |
| - | Notion token | UNKNOWN | SET; keycheck covers it |

## Repo scaffold, tooling, runner
| Item | Result |
|---|---|
| Layout (ARCH §Repo layout), `pyproject.toml`, ruff/mypy/pytest config | PASS; ruff check/format clean, mypy clean, 3 tests pass |
| pre-commit + gitleaks | PASS (`pre-commit run --all-files` passes) |
| `scripts/build-runner.sh` dry run | PASS: dummy slice `[ ]→[~]→[x]` and back |
| Planted fake key variable | PASS: runner refuses, never launches claude, marks slice `[!]`, key value not echoed (`tests/integration/test_build_runner.py`) |
| `scripts/ops/keycheck.sh`, 3 units, `install-units.sh` | WRITTEN; units pass `systemd-analyze verify`; **not installed** (needs founder sudo) |
| Full `.claude/settings.json` allowlist | **BLOCKED**: my edit to the permission file was refused by the auto-mode classifier, so I did not retry another way. Allowlist is still the bootstrap one (plus `enabledPlugins` added by the installs). Needs your decision, see below |

## Plugins and skills (G1 YES-ALL; see `skills/registry.yaml` for pinned commits)
- Installed, project scope: K1 K2 K3 K4 K5 K6 K7 K8 (official marketplace, all `enabled`).
- Copied to `.claude/skills/`: K9 K10 K11 K12 K14 K15 K16(2) K18(3) K19 differential-review, K21, K22. Each third-party one was read for scripts and grepped for network/exec/destructive patterns; nothing hostile found.
- Sentry skill-scanner is not approved yet (K20), so the "scan" was my own grep, not skill-scanner. Recorded as such.
- Flags: K10 `web-design-guidelines` tells the agent to curl a guidelines file at use time (remote instructions, treat as untrusted). K18 `systematic-debugging` includes a local bisect shell script run on demand.
- **Held back, need your answer:**
  - K19b `supply-chain-risk-auditor` (Trail of Bits): ships Python scripts that call osv.dev, npm and PyPI public APIs. SETUP lists K19 as "no code", G1 doesn't cover it. Say `YES: K19b` to install.
  - K13 (emilkowalski): two markdown files, no scripts. Safe to approve.
  - K17 (docker/skills): markdown plus two local scripts (`docker build`, `docker compose config`). Reasonable to approve; guardrails skill is markdown.
  - K20 (getsentry): `find-bugs` markdown; `skill-scanner` has one static-regex Python script (imports yaml, no network). Reasonable to approve.
  - Answer in G1 as `YES: K13 K17 K20 K19b`. Until K20 is approved, T1 review is recorded as partial.

## What you need to do
1. Install units (one sudo, read the script first): `sudo bash /home/aiorg/ai-org/scripts/ops/install-units.sh`, then `sudo -n systemctl start aiorg-keycheck.service` can be run by Claude to fill the UNKNOWN provider rows.
2. Decide on `.claude/settings.json`: either add the allowlist yourself, or tell me to proceed with a specific list (I will not self-expand permissions without that).
3. G1 second yes (above). 4. Repo URL (bootstrap B7). 5. Confirm the terms re-check is wanted.

## Gate
No hands-free running until you have read this report. `build-runner` is neither installed nor started.
