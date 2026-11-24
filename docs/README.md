# Autonomous AI Organization: Claude Code Implementation Package (v2)

This is a **design and execution specification**, not a built system. Version 2 replaces the v1 package. It keeps v1's safety gates, independent QA, evidence-based reporting and restart safety, and changes how the build is phased, which models are used, and how context is managed. `CHANGES.md` lists every change and the open questions.

## What gets built, in one paragraph
A private "company" running on the Lenovo Ubuntu server. You (the Founder) see it through a dashboard whose home page is a **live org chart**: every role is a card that lights up when its agent is working, and message lines animate when agents talk. You can chat with the organization, you get a **morning briefing** (AI news, job matches, networking targets, later consulting leads) and **alerts** in a Notion inbox, and the organization holds a **weekly lessons-learned meeting** whose outcomes become versioned policy. It runs mostly on your **existing Claude and ChatGPT subscriptions plus free tiers**, with a paid Anthropic API fallback capped at $30 a month.

## Read order
| File | Purpose | Who reads it |
|---|---|---|
| `PROJECT.md` | Charter: mission, principles, org, outcomes, success criteria | You; Claude Code in S00 only |
| `ARCHITECTURE.md` | Services, data, org runtime, provider gateway, UI | Claude Code, only the sections a slice lists |
| `PROVIDERS.md` | What your subscriptions and free tiers can and cannot legally/technically do on the server | You first; Claude Code in S00, S03 |
| `MODEL_POLICY.md` | Which model builds each slice, and which model runs each org role | Claude Code each slice (short) |
| `TASKS.md` | The 15 vertical slices, phases, tiers, model per slice, "what you'll see" | Build runner + Claude Code |
| `CLAUDE.md` | Standing rules for Claude Code, the process tiers, context rules | Auto-loaded every session (kept short) |
| `AUTONOMY.md` | What is pre-approved, what needs you, retries, stop/resume | Claude Code |
| `VALIDATION.md` | QA protocol per tier, evidence format | Claude Code |
| `SETUP.md` | Your hands-on steps, what Claude does, the prompts to type, plus the skills/plugins | You |
| `BOOTSTRAP.md` | The first Claude session: finishes server setup without sudo | Claude Code (bootstrap only) |
| `state/FOUNDER_GATES.md` | Your open decisions (G1 to G7) and the slice each one blocks | You; slices with a `Founder gate:` line |
| `DECISIONS.md` | Decision register (founder policy + technical choices) | Claude Code when a decision is needed |
| `FINAL_REPORT.md` | Evidence-based report template (not a result) | Claude Code in S14 |
| `state/HANDOFF.md` | The single state file carried between fresh sessions | Build runner + every slice |

## Where the files go
Already in place (v2.1): `CLAUDE.md` at the repo root, this package in `docs/`, state in `docs/state/` (`HANDOFF.md`, `FOUNDER_GATES.md`), subagents and commands in `.claude/`, the root setup script in `scripts/bootstrap/`, and templates in `constitution/` and `config/`.

## How the build runs (short version)
1. You do `SETUP.md` Part A (one sudo script, accounts, keys, two sign-ins). About 45 minutes.
2. You start the **bootstrap** session and watch it: Claude finishes the setup and lists anything you still owe.
3. You start **S00 interactively** over SSH and watch it (it creates the build runner).
4. You watch **S01** too. When the org chart appears in your browser, you start the runner.
5. From S02 on, `scripts/build-runner.sh` (a systemd service) runs **one fresh Claude Code session per slice**, picks the model for that slice from `TASKS.md`, pauses when your subscription usage window is exhausted and resumes after reset, and stops only at founder gates (`docs/state/FOUNDER_GATES.md`) or real blockers. You get a Notion inbox item at each phase milestone. On Claude Max, the runner uses each 5-hour window fully, waits for the reset and continues; expect about 3 to 5 slices a day (roughly 1 to 2 weeks in total).
6. At the end you read `FINAL_REPORT.md`, generated from evidence.

## First instructions
The exact prompts for bootstrap, S00 and S01 are in `SETUP.md` Part C. The first one is just `/bootstrap`.

**Honest limits.** Claude Code alone is not a durable supervisor; the build runner is deliberately simple (fresh session per slice, state in git and `HANDOFF.md`). Consumer subscriptions are licensed for personal use of the vendor's own tools; `PROVIDERS.md` explains where automated use is clearly allowed, where it is a gray area, and what the fallback is. Nothing here is a production deployment: the default target is the private staging stack on the Lenovo.
