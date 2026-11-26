#!/usr/bin/env bash
# Host-side gateway launcher (runs as user aiorg; the signed-in claude/codex CLIs live here).
#   scripts/gateway-host.sh smoke [--provider P | --api-only] [--allow-during-build]
#   scripts/gateway-host.sh echo          # claim one ready task, reply via the live gateway
# Reads only the DB password and port from the repo .env (scripts/host-env.sh; never prints values).
# Provider API keys are NOT in .env: they only exist when systemd injects them (aiorg-worker.service).
set -euo pipefail
cd "$(dirname "$0")/.."
cmd=${1:?usage: gateway-host.sh smoke|echo [args]}; shift
. scripts/host-env.sh
export AIORG_GATEWAY_MODE=live
case $cmd in
  smoke) exec .venv/bin/python -m app.gateway.cli smoke "$@" ;;
  echo)  exec .venv/bin/python -m app.workers.echo --once ;;
  *) echo "unknown command: $cmd" >&2; exit 2 ;;
esac
