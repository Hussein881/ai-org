#!/usr/bin/env bash
# Build runner (D-036; spec: docs/TASKS.md "Build runner"). One fresh `claude -p` session per slice.
# Installed root-owned at /usr/local/lib/aiorg/build-runner.sh so a slice cannot edit its own supervisor;
# changing this file means the founder re-installs it (scripts/ops/install-units.sh).
# Test hooks (env): TASKS_FILE, REPO_DIR, CLAUDE_CMD, DRY_RUN=1, RUNNER_LOG, ENV_CHECK, RECORD_DIR,
# PROBE_SECS, NOTIFY_LOG_ONLY=1.
set -u
REPO_DIR=${REPO_DIR:-/home/aiorg/ai-org}
TASKS_FILE=${TASKS_FILE:-$REPO_DIR/docs/TASKS.md}
RECORD_DIR=${RECORD_DIR:-$REPO_DIR/docs/state/slices}
CLAUDE_CMD=${CLAUDE_CMD:-claude}
RUNNER_LOG=${RUNNER_LOG:-/srv/aiorg/artifacts/logs/build-runner.log}
ENV_CHECK=${ENV_CHECK:-$REPO_DIR/scripts/check-env-clean.sh}
PROBE_SECS=${PROBE_SECS:-1200}
MAX_CONT=4
log() { echo "$(date -u +%FT%TZ) runner: $*" >> "$RUNNER_LOG" 2>/dev/null || echo "runner: $*"; }

# notify.env is loaded by the unit for alerts only. Hold the values here; they never reach
# the key check or the claude process (which is launched under env -i).
N_TOKEN=${NOTION_TOKEN:-}; N_DB=${NOTION_INBOX_DB_ID:-}
unset NOTION_TOKEN NOTION_INBOX_DB_ID NTFY_URL NTFY_TOPIC NTFY_TOKEN

notify() { # notify <title> <body>: Notion inbox item (title + body only before S05). Failure is logged, never fatal.
  log "NOTIFY: $1 | $2"
  [[ ${NOTIFY_LOG_ONLY:-0} == 1 || -z $N_TOKEN || -z $N_DB ]] && return 0
  local payload
  payload=$(python3 - "$N_DB" "$1" "$2 (@founder)" <<'PY'
import json, sys
db, title, body = sys.argv[1:4]
print(json.dumps({"parent": {"database_id": db},
  "properties": {"title": {"title": [{"text": {"content": title[:200]}}]}},
  "children": [{"object": "block", "type": "paragraph",
                "paragraph": {"rich_text": [{"text": {"content": body[:1800]}}]}}]}))
PY
  )
  printf 'header = "Authorization: Bearer %s"\nheader = "Notion-Version: 2022-06-28"\nheader = "Content-Type: application/json"\n' "$N_TOKEN" |
    curl -s -m 20 -o /dev/null -w '%{http_code}' -K - -X POST -d "$payload" https://api.notion.com/v1/pages 2>/dev/null |
    { read -r c; [[ $c == 2* ]] || log "notion post failed ($c)"; }
  return 0
}

marker_of() { grep -E "^### $1: " "$TASKS_FILE" | grep -oE '`\[.\]`$' | tr -d '`[]'; }
mark() { sed -i -E "s/^(### $1: .*)\`\[.\]\`/\1\`[$2]\`/" "$TASKS_FILE"; }
section() { sed -n "/^### $1: /,/^###\? /p" "$TASKS_FILE" | sed '1!{/^##/d}'; }
deps_done() { # all S\d+ ids named on the Depends line must be [x]
  local d; for d in $(section "$1" | grep -E 'Depends' | head -1 | sed -E 's/.*Depends//' | grep -oE 'S[0-9]+'); do
    [[ $(marker_of "$d") == x ]] || return 1; done; return 0; }
next_slice() { # [~] resumes first; else first [ ] whose dependencies are [x]
  local id
  id=$(grep -E '^### S[0-9]+: .*`\[~\]`$' "$TASKS_FILE" | head -1 | sed -E 's/^### (S[0-9]+):.*/\1/')
  [[ -n $id ]] && { echo "$id"; return; }
  for id in $(grep -E '^### S[0-9]+: .*`\[ \]`$' "$TASKS_FILE" | sed -E 's/^### (S[0-9]+):.*/\1/'); do
    deps_done "$id" && { echo "$id"; return; }; done; }
model_of() { local m; m=$(section "$1" | grep -oE 'Model `[a-z]+`' | head -1 | grep -oE '`[a-z]+`' | tr -d '`'); echo "${m:-sonnet}"; }
effort_of() { case $1 in haiku) echo low ;; *) echo high ;; esac; }  # MODEL_POLICY Part A

run_claude() { # run_claude <id> <model>; prints the final result text; returns claude's exit code
  local raw rc
  raw=$(cd "$REPO_DIR" && env -i HOME="$HOME" PATH="$PATH" USER="${USER:-aiorg}" LOGNAME="${LOGNAME:-aiorg}" \
    LANG="${LANG:-C.UTF-8}" TERM="${TERM:-dumb}" XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-}" DOCKER_HOST="${DOCKER_HOST:-}" \
    $CLAUDE_CMD -p "Run slice $1 per CLAUDE.md." --model "$2" --effort "$(effort_of "$2")" \
    --permission-mode acceptEdits --output-format json 2>>"$RUNNER_LOG"); rc=$?
  LAST_RAW=$raw
  printf '%s' "$raw" | python3 -c 'import sys,json
try: print(json.load(sys.stdin).get("result","").strip().splitlines()[-1])
except Exception: print(sys.stdin.read() if False else "")' 2>/dev/null
  return $rc
}
is_limit() { printf '%s' "$1" | grep -qiE 'usage limit|rate limit|limit reached|resets? (at|in)'; }
wait_for_reset() {
  local waited=0
  log "usage limit hit; probing every ${PROBE_SECS}s"
  while :; do
    sleep "$PROBE_SECS"; waited=$((waited + PROBE_SECS))
    out=$(env -i HOME="$HOME" PATH="$PATH" $CLAUDE_CMD -p "ok" --model haiku 2>&1) && ! is_limit "$out" && return 0
    (( waited == 21600 )) && notify "Build paused on usage limit" "Paused over 6h (likely the weekly window); runner keeps probing."
  done; }

cont=0; errs=0; skipped=" "
while :; do
  id=$(next_slice)
  for s in $skipped; do [[ $id == "$s" ]] && id=""; done
  [[ -z $id ]] && { log "no eligible slice; stopping"; exit 0; }
  if ! out=$(bash "$ENV_CHECK" 2>&1); then
    mark "$id" '!'; log "REFUSED $id: $out"; notify "Build refused: $id" "key variables in session env"
    echo "BLOCKED $id key variables in session env"; exit 1
  fi
  model=$(model_of "$id"); mark "$id" '~'; log "start $id model=$model continuation=$cont"
  if [[ ${DRY_RUN:-0} == 1 ]]; then status="SLICE_DONE $id"; mark "$id" x; echo dry-run > "$RECORD_DIR/$id.md" 2>/dev/null; rc=0
  else status=$(run_claude "$id" "$model"); rc=$?; fi
  log "end $id rc=$rc status='$status'"
  if [[ -z $status || $rc -ne 0 ]] && is_limit "${LAST_RAW:-}"; then wait_for_reset; continue; fi
  case $status in
    "SLICE_DONE $id")
      if [[ $(marker_of "$id") == x && -s ${RECORD_DIR}/$id.md ]]; then cont=0; errs=0
      else mark "$id" '!'; log "SLICE_DONE without [x] marker or slice record: $id"; notify "Build blocked: $id" "SLICE_DONE but marker or slice record missing"; skipped+="$id "; fi ;;
    "CONTINUE $id") cont=$((cont+1)); mark "$id" ' '
      (( cont > MAX_CONT )) && { mark "$id" '!'; notify "Build blocked: $id" "more than $MAX_CONT continuations"; skipped+="$id "; cont=0; } ;;
    "NEEDS_FOUNDER $id"*|"BLOCKED $id"*) mark "$id" '?'; [[ $status == BLOCKED* ]] && mark "$id" '!'
      notify "Build needs you: $id" "$status"; skipped+="$id "; cont=0 ;;
    *) errs=$((errs+1))
      if (( errs >= 2 )); then mark "$id" '!'; notify "Build blocked: $id" "error after one retry: ${status:0:200}"; skipped+="$id "; errs=0
      else mark "$id" ' '; log "error on $id, retrying once"; fi ;;
  esac
done
