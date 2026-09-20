#!/usr/bin/env bash
# Source this from the other infra scripts: loads voloridge.env and defines ssh/rsync helpers.
set -euo pipefail
VOLO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$VOLO_DIR/../.." && pwd)"
ENV_FILE="$VOLO_DIR/voloridge.env"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "missing $ENV_FILE — cp voloridge.env.example voloridge.env and fill in the instance from the booth" >&2
  exit 1
fi
set -a; source "$ENV_FILE"; set +a
: "${VOLO_HOST:?}" "${VOLO_USER:=ec2-user}" "${VOLO_KEY:=~/.ssh/voloridge-hackmit.pem}" "${VOLO_REMOTE_DIR:=~/keiko}"
VOLO_KEY="${VOLO_KEY/#\~/$HOME}"
SSH_OPTS=(-i "$VOLO_KEY" -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30 -o ConnectTimeout=10)
vssh() { ssh "${SSH_OPTS[@]}" "$VOLO_USER@$VOLO_HOST" "$@"; }
vrsync() { rsync -az --info=progress2 -e "ssh ${SSH_OPTS[*]}" "$@"; }
