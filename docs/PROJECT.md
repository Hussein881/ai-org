# Autonomous AI Organization: Project Charter
Version: 2.0 | Status: Draft for founder review | Owner: Founder (Anwar)

## Mission
Run a private, self-hosted organization of AI agents that works in parallel, 24/7, with minimal founder involvement, and delivers ready-made, curated outcomes. It plans, delegates, executes, verifies, learns and reports, while preserving founder authority, security, auditability and cost discipline.

Host: Ubuntu Server LTS on a 2016 Lenovo (model 80U0, dual-core Skylake i5, 8 GB RAM, 100 GB SSD). All inference is in the cloud; no local models.

## What the Founder gets (the outcomes the system exists for)
| Outcome | Delivered as | First available |
|---|---|---|
| Morning status briefing (overnight events, blocked work, quota/spend, decisions needed) | Notion page + dashboard | S05 |
| Urgent alerts (QA escalations, board dissent, blocked work, budget/quota exhaustion) | Notion inbox (with mention) + dashboard banner; optional phone push for critical only | S05 (channel), S08+ (sources) |
| Engineering work done by agents (e.g. features for founder projects) | Task board, QA verdicts, reports | S09 |
| A way to add departments and projects (proposal → your approval → new card on the org chart) | Dashboard form + approval queue | S12 |
| Weekly lessons-learned minutes and proposed improvements | Meeting page + approval queue | S11 |

**Projects added after the organization is formed (D-038):** AI news, job matches and networking targets, consulting leads. They are kept in the TASKS.md Project backlog (P1 to P3) and added through the S12 flow when the founder chooses.

Success is measured by the founder's own words from the design conversation: things run in parallel, with minimal involvement, as curated output.

## Operating principles
1. **Founder is the ultimate authority** over policy, budgets, high-risk actions, organizational expansion and major architecture.
2. **Founder corrections are policy.** When the founder disagrees with an agent's decision or classification, the correction becomes a versioned policy update, not just a note. The founder's correction is itself the approval.
3. **CEO** owns operational prioritization, routine plan approval, delegation and coordination, and classifies changes as major or minor. Minor changes (e.g. rewriting an underperforming agent's instructions) are autonomous; major pipeline changes need the founder.
4. **Board Advisor** (runs on Claude) challenges the CEO. When two options are about equally good, the CEO may proceed with its recommendation. On **strong disagreement**, the Board Advisor escalates to the founder, who decides.
5. **Chain of command** is enforced by the backend: agents talk to their manager, their reports, and peers they are explicitly allowed to. **Exception:** QA (and Efficiency Assurance) may escalate directly to the founder when work violates the founder's standards, an agent drifts from the plan, or an architectural problem is suspected. Direct escalations must carry evidence.
6. **Chief of Staff** keeps the founder in the loop: summarizes the organization's channel, produces the morning briefing, and brings issues that need a decision.
7. **Need-to-know context.** Every agent gets only the context it needs. Sub-agents get a clear goal and task, work independently, and **may come back and ask** when information is insufficient instead of guessing.
8. **Persistent organizational memory.** Every agent, every day, carries the founder's identity, goals, principles and preferences (the *Constitution*, see ARCHITECTURE §Memory). Agents must not drift from it over days of running.
9. **Permanent roles, temporary workers.** Roles (with memory and responsibilities) are persistent; execution agents are spun up per task and discarded.
10. **Independent QA** verifies outcomes; self-reports are never proof of completion.
11. **Process proportional to risk.** Trivial work gets no ceremony; high-risk work gets full planning, review and adversarial testing (see CLAUDE.md §Tiers).
12. **Cheap models run often; capable models lead.** Free-tier and economical models do high-frequency bulk work; capable models handle planning, judgment and review. Model assignment authority is in §Model selection.
13. **Reuse before building.** Use existing frameworks, libraries and skills (e.g. front-end design skills) rather than writing them; build our own only for governance, decision logic and what doesn't exist.
14. **Weekly lessons learned.** CEO, Board Advisor, QA, Efficiency Assurance and relevant directors meet weekly to review what worked, what didn't, founder feedback and slow areas; outcomes are proposed policy/skill changes.
15. **Backend enforcement, not prompt wording**, controls approvals, permissions, chain of command, budgets and completion gates.
16. **No invented results.** Every reported pass, cost or outcome is backed by evidence or marked UNKNOWN / NOT RUN.

## Model selection (charter-level rule)
Each role has a fixed default model set by founder-approved policy (`MODEL_POLICY.md` §Runtime). The CEO may make controlled per-task overrides within the approved provider list and quota/budget limits, and must log the reason. Moving to dynamic selection requires evidence from the usage ledger and founder approval. No agent may add a provider, raise a limit, or move founder-classified sensitive data to a provider not approved for it.

## Organization (initial)
```
                         Founder
             ┌──────────────┼───────────────┐
      Chief of Staff       CEO          Board Advisor (Claude)
                            │
            ┌───────────────┴───────────────┐
      Engineering Director        (departments you add later
            │                      through the S12 flow)
      Coding workers
       (temporary)

 Independent of the line, reporting to Founder: QA, Efficiency Assurance
```
New departments are added only through a governed change (proposal, founder approval, role card, policy).

## Non-goals for v2
Local LLM inference; Kubernetes; LangGraph/n8n (deferred, not ruled out); scraping that violates site terms or logs into sites as the founder; auto-applying to jobs or messaging people on the founder's behalf (agents draft, founder sends); unsupervised spending; public exposure of the dashboard; production access to unrelated founder systems; elaborate cost-analytics UI before data exists.

## Success criteria
- Dashboard with live org chart, chat, briefing, task board, approvals and traces is usable from Mac and iPhone over a private network.
- A morning briefing arrives daily without founder action, and every item links to its source.
- The organization runs within the approved subscription windows, free-tier quotas and (if approved) API cap; exhaustion degrades gracefully and is reported, never silently ignored.
- Founder corrections produce versioned policy changes that later agent runs demonstrably follow.
- Chain-of-command violations are blocked and audited; QA direct escalation works.
- A reboot or worker crash cannot mark unfinished work complete or duplicate side effects.
- Secrets never appear in Markdown, logs, prompts or commits.
- Every slice has reproducible evidence, a commit, and a status of verified, failed, blocked or deferred.

## Founder-approved decisions (carried from v1 and from the 2026-11-18 answers)
Project conversation timeline: yes. Routine CEO plan approvals: yes. Bounded retries/delegation: yes. Hands-free build through all approved slices: yes. Planning, coding, review and testing roles: yes, scaled by tier. Economical models when fit: yes. Final evidence-based report: yes. **New in v2:** first useful pipeline right after the hands-free milestone; build and runtime use existing subscriptions and free tiers first; everything runs on the server over SSH; Board Advisor on Claude; walking skeleton with UI from the first slice.
