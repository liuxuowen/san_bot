#!/usr/bin/env bash
set -euo pipefail

# ============ Config ============
# Remote SSH target
REMOTE_USER="root"
REMOTE_HOST="yimuliaoran.top"
SSH_PORT="22"

# Optional: SSH private key (PEM) for authentication
# Example: KEY_PATH="$HOME/.ssh/id_rsa" or id_ed25519
KEY_PATH="/Users/liuxu/peiqi.pem"

# Remote deployment directory (absolute path recommended)
REMOTE_DIR="/opt/projects/san_bot"

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
    -azh --itemize-changes
    --delete
    --chmod=Dug=rwx,Do=rx,Fug=rwX,Fo=rX
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
  echo "[1/4] Ensure remote directory exists"
  ssh_remote "mkdir -p '${REMOTE_DIR}'"

  echo "[2/4] Syncing source via rsync"
  local RSYNC_LOG=""
  RSYNC_LOG=$(mktemp)
  trap 'rm -f "${RSYNC_LOG:-}"' EXIT
  echo "- Logging rsync changes to ${RSYNC_LOG}"
  if rsync_upload "." | tee "${RSYNC_LOG}"; then
    local SUMMARY
    SUMMARY=$(grep -E '^[<>ch*]' "${RSYNC_LOG}" || true)
    if [ -n "$SUMMARY" ]; then
      echo "- Files synchronized:"
      printf '%s\n' "$SUMMARY"
    else
      echo "- Files synchronized: (no changes)"
    fi
  else
    echo "Rsync failed; see ${RSYNC_LOG:-<no-log>}" >&2
    exit 1
  fi

  echo "[3/4] Prepare Python env + install deps"
  ssh_remote "set -e; cd '${REMOTE_DIR}'; \
    if [ ! -d 'venv' ]; then python3 -m venv venv; fi; \
    . venv/bin/activate; \
    pip install --upgrade pip; \
    pip install -r requirements.txt; \
    mkdir -p uploads output"

  echo "[4/4] Code sync complete. Please log onto ${REMOTE_HOST} and start the service manually."
}

main "$@"
