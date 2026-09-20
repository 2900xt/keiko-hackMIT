#!/usr/bin/env bash
# One-time setup ON the Voloridge instance (Amazon Linux 2023). Copied over and executed by `make bootstrap`.
#   - system packages (python, git, tmux, rsync, libsndfile for soundfile, aws cli)
#   - venv at ~/keiko-venv with torch (CUDA wheel if a GPU is present, else CPU) + requirements.txt
#   - Voloridge's dataset tools synced into ~/keiko/training/voloridge/vendor/voloridge
set -euo pipefail
REMOTE_DIR="${1:-$HOME/keiko}"
VENV="$HOME/keiko-venv"

echo "== packages"
sudo dnf install -y -q python3 python3-pip python3-devel git tmux rsync htop libsndfile awscli-2 2>/dev/null \
  || sudo dnf install -y -q python3 python3-pip python3-devel git tmux rsync htop libsndfile
# AL2023 names the aws cli package differently across AMIs; either of the above lands one.

echo "== venv $VENV"
[[ -d "$VENV" ]] || python3 -m venv "$VENV"
source "$VENV/bin/activate"
pip install -q --upgrade pip wheel

if command -v nvidia-smi >/dev/null 2>&1; then
  echo "== torch (CUDA)"
  # AL2023 GPU AMIs ship the driver; the cu12x wheel bundles the runtime, so no toolkit install needed.
  pip install -q torch torchaudio --index-url https://download.pytorch.org/whl/cu124
else
  echo "== torch (CPU only — no nvidia-smi on this box)"
  pip install -q torch torchaudio --index-url https://download.pytorch.org/whl/cpu
fi
pip install -q -r "$REMOTE_DIR/training/voloridge/requirements.txt"

echo "== voloridge tools -> $REMOTE_DIR/training/voloridge/vendor/voloridge"
mkdir -p "$REMOTE_DIR/training/voloridge/vendor"
aws s3 sync --quiet --no-sign-request s3://voloridge-hack-mit-2026/src "$REMOTE_DIR/training/voloridge/vendor/voloridge"

echo "== sanity"
python - <<'PY'
import torch, numpy, librosa, boto3
print("torch", torch.__version__, "cuda", torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else "")
PY
echo "bootstrap done. activate with: source $VENV/bin/activate"
