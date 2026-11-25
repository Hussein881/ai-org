#!/usr/bin/env bash
# ExecStart of aiorg-worker.service. S04 replaces this with the durable worker loop.
# Until then it is a one-shot launcher: `touch var/smoke-requested` then
# `sudo -n systemctl start aiorg-worker.service` runs the credentialed API-provider smoke
# (systemd injects the provider keys; CLI providers are tested separately by gateway-host.sh).
cd "$(dirname "$0")/.."
if [[ -f var/smoke-requested ]]; then
  rm -f var/smoke-requested
  echo "$(date -u +%FT%TZ) aiorg-worker: gateway smoke (api providers)"
  exec scripts/gateway-host.sh smoke --api-only
fi
echo "$(date -u +%FT%TZ) aiorg-worker: nothing to do (durable worker arrives in S04)"
