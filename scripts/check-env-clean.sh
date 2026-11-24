#!/usr/bin/env bash
# Fails (exit 1) if any secret/key variable is present in this process's environment.
# Prints variable NAMES only, never values. Used by bootstrap B1, every slice session's
# first step (CLAUDE.md), and the build runner before it launches a claude session (D-036).
set -u
pattern='^(ANTHROPIC_API_KEY|ANTHROPIC_AUTH_TOKEN|CLAUDE_CODE_OAUTH_TOKEN|OPENAI_API_KEY|CODEX_API_KEY|GEMINI_API_KEY|GOOGLE_API_KEY|OPENROUTER_API_KEY|NOTION_TOKEN|NOTION_INBOX_DB_ID|NTFY_URL|NTFY_TOPIC|NTFY_TOKEN|[A-Z0-9_]*(_API_KEY|_TOKEN|_SECRET|_PASSWORD))='
# Claude Code injects its own CLAUDE_CODE_* session plumbing into tool processes; those are not
# founder keys and can't be removed from inside a session. CLAUDE_CODE_OAUTH_TOKEN still counts.
leaked=$(env | grep -E "$pattern" | cut -d= -f1 | grep -vE '^CLAUDE_CODE_' ; env | grep -E '^CLAUDE_CODE_OAUTH_TOKEN=' | cut -d= -f1)
leaked=$(echo "$leaked" | sed '/^$/d' | sort -u)
if [[ -n $leaked ]]; then
  echo "ENV_DIRTY: key variables present (names only): $(echo "$leaked" | tr '\n' ' ')"
  exit 1
fi
echo "ENV_CLEAN"
