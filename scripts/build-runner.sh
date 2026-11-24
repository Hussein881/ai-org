#!/usr/bin/env bash
# Build runner (D-036). Starts one fresh `claude -p` session per slice and reads the status line.
# Installed root-owned at /usr/local/lib/aiorg/build-runner.sh so a slice cannot edit its own supervisor.
# Changing this file means the founder re-installs it (see scripts/ops/install-units.sh).
# Test hooks (env): TASKS_FILE, REPO_DIR, CLAUDE_CMD, DRY_RUN=1, RUNNER_LOG, ONCE=1.
set -u
REPO_DIR=${REPO_DIR:-/home/aiorg/ai-org}
TASKS_FILE=${TASKS_FILE:-$REPO_DIR/docs/TASKS.md}
CLAUDE_CMD=${CLAUDE_CMD:-claude}
RUNNER_LOG=${RUNNER_LOG:-/srv/aiorg/artifacts/logs/build-runner.log}
MAX_CONT=4
ENV_CHECK=${ENV_CHECK:-$REPO_DIR/scripts/check-env-clean.sh}
log() { echo "$(date -u +%FT%TZ) runner: $*" >> "$RUNNER_LOG" 2>/dev/null || echo "runner: $*"; }
# Next slice = first one not [x]/[-]. If that one is not [ ] (in progress, blocked, needs founder), stop:
# later slices depend on it, so the runner never skips past it.
next_slice() {
  local line
  line=$(grep -E '^### S[0-9]+: .*`\[.\]`' "$TASKS_FILE" | grep -vE '`\[[x-]\]`$' | head -1)
  [[ $line =~ '`[ ]`'$ ]] && echo "$line" | sed -E 's/^### (S[0-9]+):.*/\1/'
  return 0
}
# notify.env is loaded by the unit for alerts only. Hold those values here and keep them out of
# the key check and out of the claude process (claude is launched with an env allowlist, D-036).
NOTIFY_NOTION_TOKEN=${NOTION_TOKEN:-}; NOTIFY_NOTION_DB=${NOTION_INBOX_DB_ID:-}
NOTIFY_NTFY_URL=${NTFY_URL:-}; NOTIFY_NTFY_TOPIC=${NTFY_TOPIC:-}; NOTIFY_NTFY_TOKEN=${NTFY_TOKEN:-}
unset NOTION_TOKEN NOTION_INBOX_DB_ID NTFY_URL NTFY_TOPIC NTFY_TOKEN
mark() { # mark <ID> <marker-char>
  sed -i -E "s/^(### $1: .*)\`\[.\]\`/\1\`[$2]\`/" "$TASKS_FILE"
}
cont=0
while :; do
  id=$(next_slice)
  [[ -z $id ]] && { log "no eligible slice; done"; exit 0; }
  if ! out=$(bash "$ENV_CHECK" 2>&1); then
    mark "$id" '!'; log "REFUSED $id: $out"; echo "BLOCKED $id key variables in session env"; exit 1
  fi
  mark "$id" '~'; log "start $id (continuation $cont)"
  if [[ ${DRY_RUN:-0} == 1 ]]; then status="SLICE_DONE $id"
  else
    cd "$REPO_DIR" || exit 1
    status=$(env -i HOME="$HOME" PATH="$PATH" USER="${USER:-aiorg}" LANG="${LANG:-C.UTF-8}" \
      XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-}" DOCKER_HOST="${DOCKER_HOST:-}" \
      $CLAUDE_CMD -p --model sonnet --permission-mode acceptEdits \
      "Run slice $id per CLAUDE.md." 2>>"$RUNNER_LOG" | tail -n1)
  fi
  log "end $id: $status"
  case $status in
    "SLICE_DONE $id") mark "$id" 'x'; cont=0 ;;
    "CONTINUE $id") cont=$((cont+1)); mark "$id" ' ';
        (( cont > MAX_CONT )) && { mark "$id" '!'; log "too many continuations $id"; exit 1; } ;;
    NEEDS_FOUNDER*) mark "$id" '?'; log "$status"; exit 2 ;;
    *) mark "$id" '!'; log "blocked: $status"; exit 1 ;;
  esac
  [[ ${ONCE:-0} == 1 ]] && exit 0
done
