#!/usr/bin/env bash
# One minimal authenticated request per provider. Writes PASS/FAIL <http status> only; never keys or bodies.
# Installed root-owned at /usr/local/lib/aiorg/keycheck.sh; run by aiorg-keycheck.service.
set -u
OUT=/srv/aiorg/artifacts/keycheck.txt
tmp=$(mktemp)
check() { # check <name> <url> <header-config-on-stdin>
  local code
  code=$(curl -s -o /dev/null -m 20 -w '%{http_code}' -K - "$2" 2>/dev/null) || code=000
  [[ $code == 2* ]] && echo "$1: PASS $code" >> "$tmp" || echo "$1: FAIL $code" >> "$tmp"
}
echo "# $(date -u +%FT%TZ) names and status only" > "$tmp"
if [[ -n ${GEMINI_API_KEY:-} ]]; then
  printf 'header = "x-goog-api-key: %s"\n' "$GEMINI_API_KEY" | check gemini "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1"
else echo "gemini: UNSET" >> "$tmp"; fi
if [[ -n ${OPENROUTER_API_KEY:-} ]]; then
  printf 'header = "Authorization: Bearer %s"\n' "$OPENROUTER_API_KEY" | check openrouter "https://openrouter.ai/api/v1/key"
else echo "openrouter: UNSET" >> "$tmp"; fi
if [[ -n ${ANTHROPIC_API_KEY:-} ]]; then
  printf 'header = "x-api-key: %s"\nheader = "anthropic-version: 2023-06-01"\n' "$ANTHROPIC_API_KEY" | check anthropic "https://api.anthropic.com/v1/models?limit=1"
else echo "anthropic: UNSET" >> "$tmp"; fi
if [[ -n ${NOTION_TOKEN:-} ]]; then
  printf 'header = "Authorization: Bearer %s"\nheader = "Notion-Version: 2022-06-28"\n' "$NOTION_TOKEN" | check notion "https://api.notion.com/v1/users/me"
else echo "notion: UNSET" >> "$tmp"; fi
mv "$tmp" "$OUT"; chmod 644 "$OUT"
