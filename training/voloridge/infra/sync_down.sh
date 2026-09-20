#!/usr/bin/env bash
# Pull runs/ (metrics, confusion matrices, logs, best.pt) and exported models/ back from the instance.
source "$(dirname "$0")/env.sh"
for sub in whale_cnn voloridge; do
  echo "== $sub/runs + $sub/models <- $VOLO_HOST"
  vrsync "$VOLO_USER@$VOLO_HOST:$VOLO_REMOTE_DIR/training/$sub/runs/" "$REPO_ROOT/training/$sub/runs/" 2>/dev/null || true
  vrsync "$VOLO_USER@$VOLO_HOST:$VOLO_REMOTE_DIR/training/$sub/models/" "$REPO_ROOT/training/$sub/models/" 2>/dev/null || true
done
vrsync "$VOLO_USER@$VOLO_HOST:$VOLO_REMOTE_DIR/training/voloridge/analysis/out/" "$VOLO_DIR/analysis/out/" 2>/dev/null || true
