#!/usr/bin/env bash
# ExecStart of aiorg-worker.service: the durable worker (systemd injects the provider keys).
# `touch var/smoke-requested` then restarting the unit runs the credentialed API-provider smoke
# first. The exit code reaches systemd: Restart=on-failure restarts anything but a clean stop.
set -euo pipefail
cd "$(dirname "$0")/.."
# systemd gives a bare PATH; the signed-in claude and codex CLIs live in the user's local bin
export PATH="$HOME/.local/bin:$PATH"
if [[ -f var/smoke-requested ]]; then
  rm -f var/smoke-requested
  echo "$(date -u +%FT%TZ) aiorg-worker: gateway smoke (api providers)"
  scripts/gateway-host.sh smoke --api-only || echo "$(date -u +%FT%TZ) aiorg-worker: smoke failed"
fi
. scripts/host-env.sh
export AIORG_GATEWAY_MODE=live
export AIORG_CEO_LIVE_REPLY="${AIORG_CEO_LIVE_REPLY:-true}"
export PYTHONUNBUFFERED=1
echo "$(date -u +%FT%TZ) aiorg-worker: starting durable worker"
exec .venv/bin/python -m app.workers.host
