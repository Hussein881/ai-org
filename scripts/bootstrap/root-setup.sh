#!/usr/bin/env bash
# AI Org: one-time root setup for the Lenovo (Ubuntu; tested target 26.10).
# This is the only step that needs sudo. Everything after it is done by Claude Code
# as the unprivileged user `aiorg` (see docs/BOOTSTRAP.md).
#
# Read this file before running it. It is idempotent: safe to run again.
#
#   sudo bash scripts/bootstrap/root-setup.sh                  # install and configure
#   sudo bash scripts/bootstrap/root-setup.sh --check-secrets  # after filling keys: report SET/EMPTY (never values)
#   sudo bash scripts/bootstrap/root-setup.sh --refresh-repo   # as the first form, but moves an existing
#                                                              # /home/aiorg/ai-org aside (kept) and copies this repo fresh
#
# What it does: apt update/upgrade; base packages; Node.js LTS; Docker Engine
# (with rootless extras; does NOT add anyone to the docker group); Tailscale package (does NOT
# log in); users aiorg + aiorg-coder; /srv/aiorg folders; empty secret-file templates (0600 root);
# copies your SSH key to aiorg; creates a GitHub deploy key for aiorg; copies this repo to
# /home/aiorg/ai-org; installs Claude Code (native installer, as aiorg), uv + Python 3.12 (as aiorg),
# the Codex CLI, and a narrow sudoers rule for aiorg (start/stop/restart of the AI Org services, reboot).
# What it does NOT do: change sshd config, log in to anything, store any key, open ports.
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "Run with sudo: sudo bash $0"; exit 1; }

REPO_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ADMIN_USER="${SUDO_USER:-}"
AIORG_HOME=/home/aiorg
REPO_DST="$AIORG_HOME/ai-org"
SRV=/srv/aiorg
SECRETS="$SRV/secrets"
STATUS_FILE="$SRV/artifacts/secrets-status.txt"
export DEBIAN_FRONTEND=noninteractive

say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
note() { printf '   %s\n' "$*"; }

# cd ~ first: the caller's cwd is usually the admin's home, which aiorg can't read (uv walks up looking for uv.toml).
as_aiorg() { sudo -u aiorg -H bash -lc "cd ~ && $1"; }

check_secrets() {
  say "Secret files (names only, values are never printed)"
  {
    echo "# Written by root-setup.sh --check-secrets at $(date -Is). Names only."
    echo "dir $SECRETS: owner=$(stat -c %U "$SECRETS") mode=$(stat -c %a "$SECRETS")"
    for f in providers.env notify.env; do
      p="$SECRETS/$f"
      if [[ ! -f $p ]]; then echo "$f: MISSING"; continue; fi
      echo "$f: owner=$(stat -c %U "$p") mode=$(stat -c %a "$p")"
      while IFS= read -r line || [[ -n $line ]]; do
        [[ $line =~ ^[[:space:]]*(#|$) ]] && continue
        name="${line%%=*}"; val="${line#*=}"; val="${val//[\"\' ]/}"
        if [[ -n $val ]]; then echo "  $name: SET"; else echo "  $name: EMPTY"; fi
      done < "$p"
    done
  } | tee "$STATUS_FILE"
  chown aiorg:aiorg "$STATUS_FILE"; chmod 0644 "$STATUS_FILE"
  note "Claude reads $STATUS_FILE during bootstrap. It contains no values."
}

if [[ ${1:-} == "--check-secrets" ]]; then check_secrets; exit 0; fi
if [[ ${1:-} == "--refresh-repo" ]]; then REFRESH_REPO=1; fi

say "OS"
. /etc/os-release
note "$PRETTY_NAME"
[[ $ID == ubuntu ]] || note "WARNING: not Ubuntu; the plan assumes Ubuntu Server LTS."

say "apt update + upgrade"
apt-get update -q
apt-get -y -q upgrade

say "Base packages"
apt-get -y -q install ca-certificates curl gnupg git jq unzip build-essential \
  software-properties-common python3 python3-venv python3-pip pipx \
  uidmap dbus-user-session slirp4netns fuse-overlayfs acl


say "Node.js LTS (needed by Codex CLI and Playwright)"
node_major=$(node -v 2>/dev/null | sed -E 's/^v([0-9]+).*/\1/' || echo 0)
if [[ ${node_major:-0} -lt 20 ]]; then
  curl -fsSL https://deb.nodesource.com/setup_lts.x | bash -
  apt-get -y -q install nodejs
fi
note "node $(node -v), npm $(npm -v)"

say "Docker Engine + Compose (rootless extras included; nobody is added to the docker group)"
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sh
fi
apt-get -y -q install docker-ce-rootless-extras docker-compose-plugin || true
note "$(docker --version)"

say "Tailscale (package only; you run 'sudo tailscale up' yourself)"
if ! command -v tailscale >/dev/null; then
  curl -fsSL https://tailscale.com/install.sh | sh
fi
note "$(tailscale version | head -1)"

say "Service users"
for u in aiorg aiorg-coder; do
  if id "$u" >/dev/null 2>&1; then note "$u exists"; else adduser --disabled-password --gecos "" "$u"; note "$u created"; fi
done
grep -q '^aiorg:' /etc/subuid && grep -q '^aiorg:' /etc/subgid \
  || note "WARNING: aiorg has no subuid/subgid range; rootless Docker needs one (usermod --add-subuids/--add-subgids)."
if id -nG aiorg | tr ' ' '\n' | grep -qx docker; then
  note "WARNING: aiorg is in the docker group (root-equivalent). Plan prefers rootless (T-007)."
fi
loginctl enable-linger aiorg   # lets aiorg's user services (rootless Docker, runner) run without a login
note "linger enabled for aiorg"

say "/srv/aiorg folders"
mkdir -p "$SRV"/{secrets,workspaces,backups,artifacts}
chown root:root "$SECRETS"; chmod 0700 "$SECRETS"
chown aiorg:aiorg "$SRV"/{workspaces,backups,artifacts}
if [[ ! -f $SECRETS/providers.env ]]; then
  cat > "$SECRETS/providers.env" <<'EOF'
# Fill with: sudo nano /srv/aiorg/secrets/providers.env   (never paste these anywhere else)
GEMINI_API_KEY=
OPENROUTER_API_KEY=
# Anthropic API key with a $30/month workspace limit set in the Console (D-027, D-033).
# Never export this in the aiorg shell that runs Claude Code.
ANTHROPIC_API_KEY=
EOF
fi
if [[ ! -f $SECRETS/notify.env ]]; then
  cat > "$SECRETS/notify.env" <<'EOF'
# Fill with: sudo nano /srv/aiorg/secrets/notify.env
NOTION_TOKEN=
NOTION_INBOX_DB_ID=
# Optional, critical alerts only:
NTFY_URL=
NTFY_TOPIC=
NTFY_TOKEN=
EOF
fi
chown root:root "$SECRETS"/*.env; chmod 0600 "$SECRETS"/*.env
note "secrets: $(stat -c '%U %a' "$SECRETS"); templates created if missing"

say "SSH key for aiorg (so you can 'ssh aiorg@<lenovo>')"
install -d -m 0700 -o aiorg -g aiorg "$AIORG_HOME/.ssh"
if [[ -n $ADMIN_USER && -f /home/$ADMIN_USER/.ssh/authorized_keys && ! -s $AIORG_HOME/.ssh/authorized_keys ]]; then
  cp "/home/$ADMIN_USER/.ssh/authorized_keys" "$AIORG_HOME/.ssh/authorized_keys"
  chown aiorg:aiorg "$AIORG_HOME/.ssh/authorized_keys"; chmod 0600 "$AIORG_HOME/.ssh/authorized_keys"
  note "copied $ADMIN_USER's authorized_keys to aiorg"
else
  note "aiorg already has authorized_keys, or no admin key found (skipped)"
fi

say "GitHub deploy key for aiorg"
KEY="$AIORG_HOME/.ssh/id_ed25519_github"
if [[ ! -f $KEY ]]; then
  as_aiorg "ssh-keygen -q -t ed25519 -N '' -C 'aiorg@$(hostname) deploy key' -f '$KEY'"
fi
if ! grep -q 'id_ed25519_github' "$AIORG_HOME/.ssh/config" 2>/dev/null; then
  printf 'Host github.com\n  IdentityFile ~/.ssh/id_ed25519_github\n  IdentitiesOnly yes\n' >> "$AIORG_HOME/.ssh/config"
  chown aiorg:aiorg "$AIORG_HOME/.ssh/config"; chmod 0600 "$AIORG_HOME/.ssh/config"
fi

say "Repo copy at $REPO_DST"
if [[ $REPO_SRC == "$REPO_DST" ]]; then
  note "already running from $REPO_DST"
elif [[ -e $REPO_DST && ${REFRESH_REPO:-0} == 1 ]]; then
  OLD="$REPO_DST.old-$(date +%Y%m%d-%H%M%S)"
  mv "$REPO_DST" "$OLD"; cp -a "$REPO_SRC" "$REPO_DST"; chown -R aiorg:aiorg "$REPO_DST"
  note "old copy moved to $OLD (not deleted); fresh copy placed"
elif [[ -e $REPO_DST ]]; then
  note "WARNING: $REPO_DST exists and was NOT overwritten. If it is an older plan, re-run with --refresh-repo"
else
  cp -a "$REPO_SRC" "$REPO_DST"; chown -R aiorg:aiorg "$REPO_DST"; note "copied"
fi
# A git worktree's .git is a one-line pointer file into the admin's repo, which aiorg can't read.
# Drop it so bootstrap B7 can 'git init' a repo aiorg owns. A real .git directory is left alone.
if [[ $REPO_SRC != "$REPO_DST" && -f $REPO_DST/.git ]] && grep -q '^gitdir: ' "$REPO_DST/.git"; then
  rm -f "$REPO_DST/.git"; note "removed worktree pointer $REPO_DST/.git (bootstrap B7 will git init)"
fi

say "Claude Code (native installer, as aiorg)"
if as_aiorg 'command -v claude >/dev/null || test -x ~/.local/bin/claude'; then
  note "already installed"
else
  as_aiorg 'curl -fsSL https://claude.ai/install.sh | bash'
fi
grep -q 'ANTHROPIC_API_KEY' "$AIORG_HOME"/.bashrc "$AIORG_HOME"/.profile 2>/dev/null \
  && note "WARNING: ANTHROPIC_API_KEY appears in aiorg's shell files. Remove it, or the build bills the API." || true

say "uv + Python 3.12 (as aiorg, user space; D-037)"
# Ubuntu 26.10 ships Python 3.14 and no python3.12 package; uv installs a managed 3.12 for aiorg.
if ! as_aiorg 'test -x ~/.local/bin/uv'; then
  as_aiorg 'curl -LsSf https://astral.sh/uv/install.sh | sh'
fi
as_aiorg '~/.local/bin/uv python install 3.12'
note "$(as_aiorg '~/.local/bin/uv --version'); python 3.12 at $(as_aiorg '~/.local/bin/uv python find 3.12')"

say "Narrow sudo rule for aiorg (founder-approved 2026-11-24, D-036)"
# Exactly these commands, with exactly these arguments: no shell, no pager, no editors.
# The units are installed later by the founder in S00; the rule can name them before they exist.
SUDOERS=/etc/sudoers.d/aiorg
SC=/usr/bin/systemctl
cat > "$SUDOERS.tmp" <<EOF
# AI Org: the only root commands aiorg may run (no password). Edit with: sudo visudo -f $SUDOERS
Cmnd_Alias AIORG_SVC = $SC start aiorg-worker.service, $SC stop aiorg-worker.service, $SC restart aiorg-worker.service, \\
                       $SC start build-runner.service, $SC stop build-runner.service, $SC restart build-runner.service, \\
                       $SC start aiorg-keycheck.service
Cmnd_Alias AIORG_REBOOT = $SC reboot
aiorg ALL=(root) NOPASSWD: AIORG_SVC, AIORG_REBOOT
EOF
chmod 0440 "$SUDOERS.tmp"
if visudo -cf "$SUDOERS.tmp" >/dev/null; then
  mv -f "$SUDOERS.tmp" "$SUDOERS"; note "installed $SUDOERS"
else
  rm -f "$SUDOERS.tmp"; note "ERROR: sudoers rule failed validation; NOT installed"
fi

say "Codex CLI"
command -v codex >/dev/null || npm install -g @openai/codex
note "$(codex --version 2>/dev/null || echo 'codex installed')"

say "SSH hardening (report only; this script never edits sshd)"
sshd -T 2>/dev/null | grep -Ei '^(passwordauthentication|permitrootlogin|pubkeyauthentication) ' | sed 's/^/   /' || true
note "Want: passwordauthentication no, permitrootlogin no. See docs/SETUP.md H1 to change it."

# Always refresh the key status file (names and SET/EMPTY only), so filling keys before this run needs no second sudo step.
check_secrets

say "Done. Your hands-on steps next (docs/SETUP.md, Part A):"
cat <<EOF
   1. sudo tailscale up            (open the URL it prints and approve the Lenovo)
   2. Add this deploy key to your empty private GitHub repo (Settings > Deploy keys, allow write):
      $(cat "$KEY.pub")
   3. sudo nano $SECRETS/providers.env   and   sudo nano $SECRETS/notify.env
      then: sudo bash $REPO_DST/scripts/bootstrap/root-setup.sh --check-secrets
   4. From your Mac: ssh aiorg@<lenovo>, then: cd ~/ai-org && claude     (sign in with Claude Max)
      and: codex login --device-auth                                      (sign in with ChatGPT)
EOF
