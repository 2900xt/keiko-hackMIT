#!/usr/bin/env bash
# Pretrain the whale CNN with a JSON config, on whatever GPU is here. Extra args override the config.
#   bash train/pretrain.sh configs/pretrain_gpu.json
#   bash train/pretrain.sh configs/pretrain_gpu.json --seed 3 --name volo_w64_s3 --export models/whale_cnn_volo_s3
set -euo pipefail
cd "$(dirname "$0")/.."
CFG="${1:?config json}"; shift
ARGS=$(python3 - "$CFG" <<'PY'
import json, sys
cfg = {k: v for k, v in json.load(open(sys.argv[1])).items() if not k.startswith("_")}
print(" ".join(f"--{k} {v}" for k, v in cfg.items()))
PY
)
echo "whale_cnn/train.py $ARGS $*"
nvidia-smi --query-gpu=name,memory.used --format=csv,noheader 2>/dev/null || true
cd ../whale_cnn && exec python3 train.py $ARGS "$@"
