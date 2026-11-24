---
description: Independent end-of-slice review (Codex read-only, falls back to the reviewer subagent)
---
1. Write `artifacts/review/<slice>-input.md` containing only: the slice section from docs/TASKS.md, the test output summary, and the list of changed files. (For T2 plan review, include the written plan instead of the diff.)
2. Run Codex non-interactively, read-only, in the repo, e.g.:
   `codex exec --sandbox read-only "Review the changes on this branch vs main against artifacts/review/<slice>-input.md. Verdict PASS, PASS_WITH_NOTES or FAIL; list defects as path:line — problem — evidence; max 15 lines."`
   (S00 confirms the exact flags with `codex exec --help` and records them here.)
3. If Codex fails to run or its usage window is exhausted, use the `reviewer` subagent instead and mark the review same-vendor.
4. Record the verdict, reviewer identity and model ID in the slice record. Do not argue with the verdict in the record; fix the defects or mark them as residual risk with a reason.
