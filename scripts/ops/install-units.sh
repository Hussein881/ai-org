#!/usr/bin/env bash
# Founder runs once with sudo: sudo bash /home/aiorg/ai-org/scripts/ops/install-units.sh
# Installs the runner/keycheck scripts (root-owned) and the three system units. Nothing else.
set -euo pipefail
R=/home/aiorg/ai-org
install -d -o root -g root -m 0755 /usr/local/lib/aiorg
install -o root -g root -m 0755 $R/scripts/build-runner.sh /usr/local/lib/aiorg/build-runner.sh
install -o root -g root -m 0755 $R/scripts/ops/keycheck.sh /usr/local/lib/aiorg/keycheck.sh
install -m 0644 $R/scripts/ops/systemd/{build-runner,aiorg-worker,aiorg-keycheck}.service /etc/systemd/system/
mkdir -p /srv/aiorg/artifacts/logs && chown aiorg:aiorg /srv/aiorg/artifacts/logs
systemctl daemon-reload
systemctl enable build-runner.service aiorg-worker.service
