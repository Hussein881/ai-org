# Founder gates (your decisions; Claude never fills these in)
Each slice with a `Founder gate:` line reads its gate here before starting. **If the gate is unanswered when that slice starts, the slice exits `NEEDS_FOUNDER` and the runner posts a Notion inbox item.** Answer them before you start the runner to keep the build hands-free.

To answer: edit this file (`nano ~/ai-org/docs/state/FOUNDER_GATES.md`), or tell Claude in a session, e.g. "Record in FOUNDER_GATES: G1 yes to all, G5 no." Write `Answer:` as shown and the date.

---

### G1. D-034: install the skills and plugins that run code (needed by S00)
The "Runs code" items in SETUP §3: **context7** (MCP server; public library questions go to a third-party service), **security-guidance** (hooks), **pyright-lsp** (pyright binary), **webapp-testing** (Python helper scripts), **skill-creator** (eval scripts). Plus three S00 inspects first and reports back: Emil Kowalski's animation skills (K13), Docker's skills (K17), Sentry's skills (K20).
- Options: `YES-ALL` · `YES: <ids>` (e.g. `YES: K6 K7 K14`) · `NO`
- If unanswered at S00: S00 does **not** stop. It installs only the items that don't run code, skips the rest, and lists them as skipped in the preflight report. You can answer later and re-run that S00 step.
- For the three "check in S00" items, S00 reports what they run; they need a second yes here (`YES: K13 K17 K20`) after you've read that.
- Founder rule (2026-11-24): until K20 is approved, T1 slices review with Codex + `/code-review` + the `reviewer` subagent and record the review as **partial** instead of blocking.

Answer: YES-ALL (founder, 2026-11-24). K13, K17, K20: <pending: founder decides after reading S00's scan report>

### G2. Docker mode (needed by S01, only if rootless failed)
Bootstrap tries rootless Docker (T-007, preferred). If it failed, `docs/state/bootstrap.md` says why. Options: `FIX-ROOTLESS` (you run the fix it lists) · `ACCEPT-DOCKER-GROUP` (adds `aiorg` to the docker group, which is root-equivalent; recorded as an accepted risk in DECISIONS T-007).
- If bootstrap shows rootless PASS, write `Answer: N/A`.
- Founder instruction (2026-11-24): bootstrap or S00 may write `N/A` here **only** if rootless Docker PASSES; on FAIL, leave it unanswered for the founder.

Answer: N/A (rootless Docker PASS in bootstrap, 2026-11-24)

### G3. Quota and budget envelopes (needed by S03)
SETUP §5: accept or change the defaults in MODEL_POLICY Part B. Options: `ACCEPT-DEFAULTS` · `CHANGE: <what>`.

Answer: ACCEPT-DEFAULTS (founder, 2026-11-24)

### G4. Constitution filled (needed by S05); career targets only when backlog P2 is added
`constitution/founder.md` (S05) is final. `config/career.yaml` is needed only when you add the Career project (Project backlog P2, D-038). Claude can interview you to draft them (bootstrap step B9). Options: `FINAL` · `CONSTITUTION-ONLY` (S05 can run, S06 waits).

Answer: <unanswered>

### G5. P-3: LinkedIn job alerts by email (needed only when backlog P2, Career, is added; D-038)
CHANGES.md §P-3. Career Intelligence would parse LinkedIn job-alert emails sent to a dedicated mailbox, instead of only official company job boards. About half a slice more in S06. If yes, you also create that mailbox and add its IMAP details to `/srv/aiorg/secrets/notify.env` (S06 names the variables).
- Options: `YES` · `NO` (P2 builds the job-board-only version)

Answer: <unanswered>

### G6. P-4: two-way Notion approvals and semantic memory (needed by S10 and S11)
CHANGES.md §P-4, two separate parts:
- **G6a (S10):** Approve/Reject properties in the Notion inbox that the worker polls, so you can approve from your phone. Options: `YES` · `NO` (approvals stay in the dashboard only).
- **G6b (S11):** `pgvector` semantic retrieval for lessons and corrections. Changes T-006 (plain full-text search). Options: `YES` · `NO`.

Answer G6a: <unanswered>
Answer G6b: <unanswered>

### G7. Backup destination (needed by S13)
SETUP §6: external disk, NAS, or encrypted cloud bucket, plus retention. Options: `<destination>, keep <N> days`.

Answer: <unanswered>

---
Not gates (your call any time, nothing waits on them): buying ~$10 of OpenRouter credit to raise its free limit; setting up ntfy for critical alerts.
