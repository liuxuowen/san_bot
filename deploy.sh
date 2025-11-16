#!/usr/bin/env bash
set -euo pipefail

# ============ Config ============
# Remote SSH target
REMOTE_USER="root"
REMOTE_HOST="yimuliaoran.top"
SSH_PORT="22"

# Optional: SSH private key (PEM) for authentication
# Example: KEY_PATH="$HOME/.ssh/id_rsa" or id_ed25519
KEY_PATH=""

# Remote deployment directory (absolute path recommended)
REMOTE_DIR="/opt/projects/san_bot"

# Optional: systemd service name (uncomment to use)
# SERVICE_NAME="san-bot"

# Optional: custom start command when not using systemd
# It should daemonize (nohup/screen/tmux). We'll default to nohup start.sh
START_CMD="nohup bash -lc './start.sh' > san_bot.out 2>&1 &"

# Exclusions for rsync (local paths)
EXCLUDES=(
  ".git/"
  ".github/"
  ".venv/"
  "venv/"
  "__pycache__/"
  ".pytest_cache/"
  ".mypy_cache/"
  "uploads/*"
  "output/*"
  "*.pyc"
  "*.pyo"
)

# ============ Helpers ============
rsync_upload() {
  local src_dir="$1"
  local dest="${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}"
  local SSH_E="ssh -p ${SSH_PORT}"
  if [ -n "${KEY_PATH:-}" ]; then
    SSH_E+=" -i ${KEY_PATH}"
  fi
  local -a args=(
    -az
    --delete
    --chmod=Dug=rwx,Do=rx,Fug=rw,Fo=r
    -e "$SSH_E"
  )
  for ex in "${EXCLUDES[@]}"; do args+=(--exclude "$ex"); done
  rsync "${args[@]}" "$src_dir"/ "$dest"/
}

ssh_remote() {
  local -a ssh_arr=("ssh" "-p" "$SSH_PORT")
  if [ -n "${KEY_PATH:-}" ]; then
    ssh_arr+=("-i" "$KEY_PATH")
  fi
  ssh_arr+=("${REMOTE_USER}@${REMOTE_HOST}")
  "${ssh_arr[@]}" "$@"
}

# ============ Deploy Steps ============
main() {
  echo "[1/5] Ensure remote directory exists"
  ssh_remote "mkdir -p '${REMOTE_DIR}'"

  echo "[2/5] Syncing source via rsync"
  rsync_upload "."  # current repo root

  echo "[3/5] Prepare Python env + install deps"
  ssh_remote "set -e; cd '${REMOTE_DIR}'; \
    if [ ! -d 'venv' ]; then python3 -m venv venv; fi; \
    . venv/bin/activate; \
    pip install --upgrade pip; \
    pip install -r requirements.txt; \
    mkdir -p uploads output"

  echo "[4/5] Restarting service or app"
  if [ -n "${SERVICE_NAME:-}" ]; then
    ssh_remote "sudo systemctl daemon-reload || true; sudo systemctl restart '${SERVICE_NAME}'"
    echo "- Restarted systemd service: ${SERVICE_NAME}"
  else
    # Try to stop existing app (best-effort)
    ssh_remote "pkill -f 'python app.py' || true; pkill -f 'gunicorn .*app:app' || true"
    # Start with nohup using start.sh (creates venv 'venv' and runs python app.py)
    ssh_remote "cd '${REMOTE_DIR}'; ${START_CMD}"
    echo "- Started app with nohup using start.sh"
  fi

  echo "[5/5] Done. Remote path: ${REMOTE_DIR}"
}

main "$@"
