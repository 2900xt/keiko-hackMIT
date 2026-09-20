# Voloridge track: training on their AWS box + the NOAA ISD noise-floor join. See README.md.
SHELL := /bin/bash
PY ?= $(shell [ -x ../../.venv/bin/python ] && echo ../../.venv/bin/python || echo python3)   # same venv as pipeline/Makefile
PRETRAIN_CFG ?= configs/pretrain_gpu.json
FINETUNE_CFG ?= configs/finetune_charles.json
ISD_YEARS ?= 2024:2025   # the public ISD archive ends 2025-08-27; `make nws` covers recent weeks

.PHONY: help check bootstrap sync-up sync-code sync-down gpu-check pretrain pretrain-seeds finetune logs ls \
        tools isd isd-parse nws charles-manifest charles-features noise-floor join all-local

help: ## this
	@grep -E '^[a-z][a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  %-18s %s\n", $$1, $$2}'

# ---- instance ---------------------------------------------------------------
check: ## ssh in, print GPU / disk / region / IAM role
	infra/check.sh
bootstrap: sync-code ## one-time: packages, venv, torch, voloridge tools on the instance
	source infra/env.sh && vssh "bash $$VOLO_REMOTE_DIR/training/voloridge/infra/bootstrap_instance.sh $$VOLO_REMOTE_DIR"
sync-up: ## code + feature tensors + Charles wavs -> instance
	infra/sync_up.sh
sync-code: ## code only -> instance
	infra/sync_up.sh --code
sync-down: ## runs/ + models/ + analysis/out <- instance
	infra/sync_down.sh
gpu-check: ## fwd/bwd timing of the pretrain config on the instance
	infra/remote.sh sh $(PY) training/voloridge/infra/gpu_check.py

# ---- training (on the instance, detached) -----------------------------------
pretrain: ## whale_cnn pretrain with $(PRETRAIN_CFG), detached tmux
	infra/remote.sh run $$($(PY) -c "import json;print(json.load(open('$(PRETRAIN_CFG)'))['name'])") \
	    "cd training/voloridge && bash train/pretrain.sh $(PRETRAIN_CFG)"
pretrain-seeds: ## same config, seeds 1-4, one tmux each (needs the GPU memory for 4 runs, or run sequentially)
	for s in 1 2 3 4; do infra/remote.sh run volo_w64_s$$s "cd training/voloridge && bash train/pretrain.sh $(PRETRAIN_CFG) --seed $$s --name volo_w64_s$$s --export models/whale_cnn_volo_s$$s"; done
finetune: ## fine-tune on Charles features with $(FINETUNE_CFG), detached tmux
	infra/remote.sh run $$($(PY) -c "import json;print(json.load(open('$(FINETUNE_CFG)'))['name'])") \
	    "cd training/voloridge && $(PY) train/finetune.py --config $(FINETUNE_CFG)"
logs: ## tail a run: make logs RUN=volo_w64
	infra/remote.sh logs $(RUN)
ls: ## tmux sessions + GPU utilisation on the instance
	infra/remote.sh ls

# ---- data + analysis (local or instance, no GPU) ----------------------------
tools: ## Voloridge's per-dataset fetch tools -> vendor/voloridge
	data/fetch_voloridge_tools.sh
isd: tools ## NOAA ISD slice for configs/stations.txt, years $(ISD_YEARS) -> data/noaa_isd/
	PY=$(PY) data/fetch_isd.sh $(ISD_YEARS)
isd-parse: ## fixed-width .gz -> data/isd_hourly.csv
	$(PY) data/parse_isd.py
nws: ## last 7 days of live KBOS obs (same station, pre-archive) merged into data/isd_hourly.csv
	$(PY) data/fetch_nws.py --merge
charles-manifest: ## pipeline/out/*.wav -> data/charles_clips.csv (fill in the label column)
	$(PY) data/charles_manifest.py
charles-features: ## data/charles_clips.csv -> data/charles_v2/{windows.npy,manifest.csv,labels.json}
	$(PY) data/charles_features.py
noise-floor: ## pipeline/out/*.wav -> analysis/out/noise_floor_hourly.csv
	$(PY) analysis/noise_floor.py
join: ## noise floor x ISD -> analysis/out/noise_vs_weather.{csv,png} + summary.json
	$(PY) analysis/join_isd.py
all-local: isd isd-parse nws noise-floor join ## the whole ISD side, no instance needed
