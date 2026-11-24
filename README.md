# AI Org (private)
A self-hosted "AI organization" built by Claude Code on the Lenovo, slice by slice. The full plan is in `docs/` (start with `docs/README.md`).

## Start here
1. **Your hands, about 45 minutes:** `docs/SETUP.md` Part A. One `sudo` script (`scripts/bootstrap/root-setup.sh`), then accounts, keys and two sign-ins.
2. **Claude finishes setup:** `ssh aiorg@<lenovo>`, `cd ~/ai-org`, `claude --model sonnet --permission-mode acceptEdits`, type `/bootstrap`. Watch it; it ends with anything you still owe.
3. **Answer your gates** in `docs/state/FOUNDER_GATES.md` (G1 first).
4. **S00 and S01 watched, then hands-free:** prompts in `docs/SETUP.md` Part C.

Emergency stop and credential revocation: `docs/SETUP.md` §6.
