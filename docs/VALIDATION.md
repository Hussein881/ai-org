# Validation, Independent QA and Evidence
Validation effort scales with the tier (CLAUDE.md §Process tiers). The cross-cutting criteria below are checked where a slice touches them and all together in S14.

## QA by tier
| | T0 Trivial | T1 Standard | T2 High-risk |
|---|---|---|---|
| Deterministic checks | lint, format, affected tests | + slice acceptance tests, Playwright smoke for the visible change | + full suite, negative/adversarial tests named in the slice |
| Independent review | none | one pass at slice end: Codex (cross-vendor) + `/code-review` + `find-bugs`; while `find-bugs` (K20) isn't approved, Codex + `/code-review` + `reviewer` subagent, recorded as **partial** | Codex review of the written plan before code; then Codex + `/code-review` + `pr-review-toolkit` + `differential-review` on the result |
| Reviewer input | n/a | diff, acceptance criteria, test output, slice record. **Not** the implementer's conversation. | same + threat list from the plan |
| Repair | 1 round | ≤2 rounds | ≤2 rounds, then model escalation, then `[!]` |

Reviewer verdicts: `PASS`, `PASS_WITH_NOTES` (notes go to residual risks), `FAIL` (defects listed with file:line and a failing test or concrete reason). Model judgment supplements tests; it never replaces a failing deterministic test.

If Codex is unavailable, the `reviewer` subagent (Opus 5.5, fresh context) reviews and the slice record says **same-vendor review**. A slice with no review of any kind cannot be `[x]`. A **partial** review (founder rule 2026-11-24: K20 not yet approved) does not block `[x]`; the slice record and FINAL_REPORT say partial.

## UI quality gate (every slice that changes the UI)
- Playwright screenshots of each changed page at desktop (1440×900) and phone (390×844) in light and dark mode, saved to `artifacts/screens/<slice>/`; the reviewer looks at them, not just the code.
- `@axe-core/playwright`: zero serious or critical accessibility violations.
- Every data view has loading, empty and error states; no console errors or React warnings in the smoke run.
- `web-design-guidelines` review passes; motion reviewed with `review-animations` where the slice adds animation.
- Uses theme tokens and shadcn/ui components (no ad-hoc colors or one-off duplicates of existing components).
- Org chart: 60 fps pan/zoom isn't measurable here, so the check is "no layout jank with all roles and 50 live events" in the Playwright trace.

## Test layers
Unit (pytest; Vitest + React Testing Library for components); migration up/down; OpenAPI-type freshness check; API integration; gateway with fake providers (routing, data_class, quota, fallback, redaction); Playwright smoke per visible feature (desktop + phone viewport); orchestration E2E with fakes; restart/crash tests (S04 onward); security tests (auth, CSRF, chain of command, sandbox); controlled live-provider smoke tests (marked, quota-aware, never in CI loops).

## Cross-cutting acceptance (checked in S14)
1. **Permissions:** unauthorized role/tool/action denied by backend and audited.
2. **Chain of command:** disallowed messages rejected; QA/EA/Board escalations to founder work and carry evidence.
3. **Isolation:** coding workers can't reach secrets, other worktrees or the Docker socket.
4. **Durability:** tasks, messages, approvals, events, policies, briefings survive restart.
5. **Idempotency:** retries do not duplicate external effects.
6. **Traceability:** briefing item/alert → task → message → run → gateway call → test → diff is navigable.
7. **No self-certification:** completion requires a QA record.
8. **Quota/budget:** exhausted envelope stops that provider's use; paid providers are unusable without approval.
9. **Data routing:** `founder_private` data never reaches a free-tier provider (ledger audit).
10. **Founder authority:** corrections create policy versions that later runs follow; governance can't be changed by agents.
11. **Failure safety:** timeout, provider outage, worker crash, QA rejection end in safe, visible states.
12. **Usability:** dashboard and chat work on desktop and iPhone over Tailscale; login/session protections tested.
13. **Backups:** restore into a clean stack succeeds.

## Evidence format
Each result: test ID, command, environment, timestamp, exit code, PASS/FAIL, log path, commit. Missing execution is `NOT RUN`, never `PASS`. Review records include reviewer identity (e.g. "codex, model <id>" or "claude opus 5.5, same-vendor").
