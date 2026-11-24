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
N_TOKEN=${NOTION_TOKEN:-}; N_DB=${NOTION_INBOX_DB_ID:-}; N_USER=${NOTION_FOUNDER_USER_ID:-}  # N_USER optional
unset NOTION_TOKEN NOTION_INBOX_DB_ID NOTION_FOUNDER_USER_ID NTFY_URL NTFY_TOPIC NTFY_TOKEN

notify() { # notify <title> <body>: Notion inbox item (title + body only before S05). Failure is logged, never fatal.
  log "NOTIFY: $1 | $2"
  [[ ${NOTIFY_LOG_ONLY:-0} == 1 || -z $N_TOKEN || -z $N_DB ]] && return 0
  local payload
  payload=$(python3 - "$N_DB" "$1" "$2" "$N_USER" <<'PY'
import json, sys
db, title, body, user = sys.argv[1:5]
rt = [{"text": {"content": body[:1800]}}]
rt.append({"mention": {"user": {"id": user}}} if user else {"text": {"content": " @founder"}})
print(json.dumps({"parent": {"database_id": db},
  "properties": {"title": {"title": [{"text": {"content": title[:200]}}]}},
  "children": [{"object": "block", "type": "paragraph", "paragraph": {"rich_text": rt}}]}))
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

SCRUB=(HOME="$HOME" PATH="$PATH" USER="${USER:-aiorg}" LOGNAME="${LOGNAME:-aiorg}" LANG="${LANG:-C.UTF-8}"
       TERM="${TERM:-dumb}" XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-}" DOCKER_HOST="${DOCKER_HOST:-}")
RAW=$(mktemp); trap 'rm -f "$RAW"' EXIT

env_clean() { # runner's own env (notify vars already held back) and the scrubbed env must both print exactly ENV_CLEAN
  local o; o=$(bash "$ENV_CHECK" 2>&1) && [[ $o == ENV_CLEAN ]] || { ENV_MSG=$o; return 1; }
  o=$(env -i "${SCRUB[@]}" bash "$ENV_CHECK" 2>&1) && [[ $o == ENV_CLEAN ]] || { ENV_MSG=$o; return 1; }
}
use_slice_branch() { # resume on the slice's own branch if it exists; a failed checkout is an error
  local b; b=$(git -C "$REPO_DIR" branch --list "slice/$1-*" --format='%(refname:short)' | head -1)
  [[ -z $b ]] || [[ $(git -C "$REPO_DIR" branch --show-current) == "$b" ]] || git -C "$REPO_DIR" checkout -q "$b" 2>>"$RUNNER_LOG"
}
# run_claude <id> <model>: sets globals STATUS (final line of the result) and RC; raw output kept in $RAW.
run_claude() {
  (cd "$REPO_DIR" && env -i "${SCRUB[@]}" $CLAUDE_CMD -p "Run slice $1 per CLAUDE.md." --model "$2" \
    --effort "$(effort_of "$2")" --permission-mode acceptEdits --output-format json) >"$RAW" 2>&1
  RC=$?
  STATUS=$(python3 -c 'import sys,json
try: print(json.load(open(sys.argv[1])).get("result","").strip().splitlines()[-1])
except Exception: print("")' "$RAW" 2>/dev/null)
  log "claude rc=$RC (raw output kept only in memory of this run; not logged)"
}
is_limit() { grep -qiE 'usage limit|rate limit|limit reached|resets? (at|in)' "$RAW"; }
wait_for_reset() { # honour a reset time in the error text; otherwise probe every PROBE_SECS
  local when target now wait
  when=$(grep -oiE 'resets? (at )?[0-9]{1,2}(:[0-9]{2})? ?(am|pm)?( \(?[A-Za-z/_]+\)?)?' "$RAW" | head -1 | sed -E 's/^resets? (at )?//I')
  now=$(date +%s); target=""
  [[ -n $when ]] && target=$(date -d "$when" +%s 2>/dev/null) && (( target <= now )) && target=$((target + 86400))
  if [[ -n $target ]] && (( target - now < 8 * 86400 )); then
    wait=$((target - now + 60)); log "usage limit; resume at $(date -d "@$target" -u +%FT%TZ)"
    (( wait > 21600 )) && notify "Build paused on usage limit" "Expected resume $(date -d "@$target" -u +%FT%TZ)."
    sleep "$wait"; return 0
  fi
  log "usage limit, no reset time given; probing every ${PROBE_SECS}s"
  local waited=0 out
  while :; do
    sleep "$PROBE_SECS"; waited=$((waited + PROBE_SECS))
    out=$(env -i "${SCRUB[@]}" $CLAUDE_CMD -p "ok" --model haiku 2>&1) && ! grep -qiE 'usage limit|rate limit|limit reached' <<<"$out" && return 0
    (( waited >= 21600 && waited < 21600 + PROBE_SECS )) && notify "Build paused on usage limit" "Over 6h with no reset time (likely the weekly window); still probing."
  done; }

phase_done() { # all slices in $1's phase are [x] or [-]
  local ph; ph=$(awk -v id="$1" '/^## Phase/{p=$0} $0 ~ "^### " id ": "{print p; exit}' "$TASKS_FILE")
  [[ -n $ph ]] || return 1
  awk -v ph="$ph" '$0==ph{on=1;next} /^## /{on=0} on && /^### S[0-9]+: /{ if ($0 !~ /`\[[x-]\]`$/) bad=1 } END{exit bad}' "$TASKS_FILE" && echo "$ph"
}

declare -A CONT ERRS; skipped=" "
while :; do
  id=$(next_slice)
  for s in $skipped; do [[ $id == "$s" ]] && id=""; done
  [[ -z $id ]] && { log "no eligible slice; stopping"; exit 0; }
  if ! env_clean; then
    mark "$id" '!'; log "REFUSED $id: $ENV_MSG"; notify "Build refused: $id" "key variables in session env"
    echo "BLOCKED $id key variables in session env"; exit 1
  fi
  model=$(model_of "$id"); prev=$(marker_of "$id"); mark "$id" '~'
  log "start $id model=$model continuation=${CONT[$id]:-0} retries=${ERRS[$id]:-0}"
  if [[ ${DRY_RUN:-0} == 1 ]]; then # prove the transition, then put everything back and stop
    had=0; [[ -e $RECORD_DIR/$id.md ]] && had=1
    mark "$id" x; log "dry-run: $id [ ]→[~]→[x]"; mark "$id" "$prev"; (( had )) || rm -f "$RECORD_DIR/$id.md"
    log "dry-run: $id restored to [$prev]"; echo "DRY_RUN ok $id"; exit 0
  fi
  if ! use_slice_branch "$id"; then STATUS=""; RC=1; : >"$RAW"; log "cannot check out slice branch for $id"
  else run_claude "$id" "$model"; fi
  log "end $id rc=$RC status='$STATUS'"
  if [[ $RC -ne 0 || -z $STATUS ]] && is_limit; then wait_for_reset; continue; fi  # not a failure, no continuation used
  case $STATUS in
    "SLICE_DONE $id")
      if [[ $(marker_of "$id") == x && -s $RECORD_DIR/$id.md ]]; then
        CONT[$id]=0; ERRS[$id]=0
        ph=$(phase_done "$id") && notify "Milestone: ${ph#\#\# } complete" "All slices in this phase are [x]. Tag it phase-<letter>-done after your review."
      else mark "$id" '!'; notify "Build blocked: $id" "SLICE_DONE but marker or slice record missing"; skipped+="$id "; fi ;;
    "CONTINUE $id") CONT[$id]=$(( ${CONT[$id]:-0} + 1 )); mark "$id" '~'  # stays [~]: resumes first, fresh session
      (( CONT[$id] > MAX_CONT )) && { mark "$id" '!'; notify "Build blocked: $id" "more than $MAX_CONT continuations"; skipped+="$id "; } ;;
    "NEEDS_FOUNDER $id"*) mark "$id" '?'; notify "Build needs you: $id" "$STATUS"; skipped+="$id " ;;
    "BLOCKED $id"*) mark "$id" '!'; notify "Build blocked: $id" "$STATUS"; skipped+="$id " ;;
    *) ERRS[$id]=$(( ${ERRS[$id]:-0} + 1 ))
      if (( ERRS[$id] >= 2 )); then mark "$id" '!'; notify "Build blocked: $id" "error after one retry (rc=$RC)"; skipped+="$id "
      else mark "$id" '~'; log "error on $id, retrying once"; fi ;;
  esac
done
