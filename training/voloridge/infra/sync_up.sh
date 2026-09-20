#!/usr/bin/env bash
# Push the repo's training/ tree (code + feature tensors, not raw audio) and pipeline/out clips to the instance.
#   ./sync_up.sh            # code + features
#   ./sync_up.sh --code     # code only (fast; use after editing a script)
source "$(dirname "$0")/env.sh"
MODE="${1:-all}"
vssh "mkdir -p $VOLO_REMOTE_DIR/training $VOLO_REMOTE_DIR/pipeline"
EXCL=(--exclude '.git' --exclude '__pycache__' --exclude '*.pyc' --exclude '.venv' --exclude 'venv'
      --exclude 'training/dataset/audio' --exclude 'training/dataset/raw' --exclude 'training/dataset/*.sqlite*'
      --exclude 'training/voloridge/vendor' --exclude 'training/voloridge/voloridge.env' --exclude 'runs/' --exclude '*.ipynb')
if [[ "$MODE" == "--code" ]]; then EXCL+=(--exclude '*.npy' --exclude '*.npz' --exclude '*.wav' --exclude '*.pt' --exclude '*.onnx'); fi
echo "== training/ -> $VOLO_HOST:$VOLO_REMOTE_DIR/training"
vrsync "${EXCL[@]}" "$REPO_ROOT/training/" "$VOLO_USER@$VOLO_HOST:$VOLO_REMOTE_DIR/training/"
if [[ "$MODE" != "--code" ]]; then
  echo "== pipeline/out (Charles recordings) -> $VOLO_HOST"
  vrsync --include '*/' --include '*.wav' --exclude '*' "$REPO_ROOT/pipeline/out/" "$VOLO_USER@$VOLO_HOST:$VOLO_REMOTE_DIR/pipeline/out/"
fi
