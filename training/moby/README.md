# Moby: two-branch ensemble right-whale detector

PyTorch version of the ISEF poster model (*MobyGlobal: Real-Time Right Whale Detection Network Powered by a Two-Branch
Ensemble Learning Model*, Figure 8), trained on the 30,000 Cornell / Kaggle Whale Detection Challenge clips
(2 s @ 2 kHz, 7,027 North Atlantic right whale upcalls vs 22,973 noise). Right whale only for now.

## Pipeline

```
whale-detection-challenge.zip ──features.py──▶ ../dataset/features/moby_narw.npz ──train.py──▶ models/moby_narw.pt (+ .json, .onnx)
                                                                                                        │
                                                                                   predict.py file.wav ◀┘
```

```bash
pip install torch numpy librosa soundfile scikit-learn onnx
python3 features.py      # ~5 min on 8 cores: 11 librosa features per clip (poster Figure 6)
python3 train.py         # 5-fold ensemble, ~15 min on an M-series GPU
python3 predict.py some_hydrophone_recording.wav
```

**Features** (`features.py`, per 2 s clip, 126 frames of 16 ms):
- 2D branch, one 103 x 126 "image": log-mel (64 bins, 20-1000 Hz) | MFCC (20) | chroma (12) | spectral contrast (7)
- 1D branch, 7 x 126: log-RMS, spectral centroid, bandwidth, rolloff, flatness, zero-crossing rate, f0 (YIN 40-500 Hz)
- Raw values are stored (float16); per-row z-scoring is a buffer inside the model, so `predict.py` feeds raw features.

**Model** (`train.py`, ~358k parameters per fold model; poster: 343,877):
- 2D: Conv2d 1→16→32→64→128 (3x3, BN, ReLU, 2x2 max-pool) → CBAM (channel + spatial attention) → global mean ‖ max → 256
- 1D: Conv1d 7→64→128 (k5, BN, ReLU, max-pool 2) → bidirectional LSTM(64) → mean over time → 128
- Head: concat 384 → 256 → 64 → 2, softmax
- **Ensemble** = mean softmax of the K fold models (`Ensemble` in `train.py`; that is what `models/moby_narw.pt` holds).

**Training**: 15% of clips are held out as the test set (stratified, seed 0). The other 85% is split into 5 stratified folds;
each fold model trains on 4 folds with AdamW + one-cycle LR, class-weighted cross-entropy (sqrt inverse frequency) with
label smoothing, and early-stops on its own fold's AUROC. Augmentation on the GPU batch, train only: Gaussian blur on the
2D stack (p = 0.5), time dilation 0.85-1.15x applied to both branches together, additive gain jitter, one time mask.

## Adding Watkins (`watkins_features.py`)

The Watkins Marine Mammal Sound Database cuts in `~/Projects/marine-sounds-db` go through the *same* `clip_features()`
so they can be trained on with the Kaggle rows unchanged:

```bash
python3 watkins_features.py --merge      # ~15 s: moby_watkins.npz (+ .csv manifest) and moby_narw_watkins.npz = Kaggle + Watkins
python3 train.py --features ../dataset/features/moby_narw_watkins.npz
```

What it does differently from the Kaggle path, and why (details in the script docstring):

| step | rule | reason |
|---|---|---|
| species | right (N. Atlantic + southern), bowhead, humpback, gray only | Moby's Nyquist is 1 kHz; these keep ≥ 87 % of their energy below it, dolphins and killer whales keep ≤ 10 % and would be hiss labelled "whale" |
| sample rate | drop cuts digitised below 2 kHz | every Watkins fin whale is 320–640 Hz; upsampled, the empty band above their Nyquist is a recorder shortcut |
| length | drop < 0.8 s; centre-pad shorter-than-2 s cuts by **reflection**; longer cuts give ≤ 5 windows ≥ 1 s apart | zero padding puts a silent block in log-RMS / flatness / ZCR that no Kaggle clip has |
| level | each window's peak is drawn from the Kaggle peak distribution (deterministic per window) | Kaggle clips are not normalised (peak 0.01–1.0); a fixed Watkins level would be a domain cue |
| split | 15 % of *tapes* held out (`split` array; Watkins ID prefix = tape) | cuts from one tape are near-duplicates |
| wild only | location matching aquarium / tank / pool / lab dropped | captive recordings |

Yield: 1,482 cuts → 3,073 windows (humpback 1,518, bowhead 957, N. Atlantic right 475, southern right 66, gray 57)
over 47 tapes, 379 windows on held-out tapes. All rows are `y = 1`: Watkins has no noise cuts.

`moby_narw_watkins.npz` has `X2`, `X1`, `y` (what `train.py` reads) plus `source`, `group`, `species`, `split`.
`train.py` currently splits by clip, so two things to check on a merged model: (1) evaluate on the Kaggle-only rows of the
test split, because the only negatives are Kaggle noise and the model can learn "analog tape vs MARU buoy" instead of
"whale vs noise"; (2) hold out whole tapes (`group`) rather than windows when reporting Watkins numbers.

## Results

RESULTS_PLACEHOLDER

## Files

| Path | What |
|---|---|
| `features.py` | Kaggle zip → `moby_narw.npz` (`X2` (N,103,126), `X1` (N,7,126), `y`); `clip_features(audio)` is reused by `predict.py` |
| `train.py` | model (`Moby`, `CBAM`, `Ensemble`), K-fold training, evaluation, export; `load_ensemble(path)` |
| `predict.py` | slide 2 s windows over any audio file, print P(whale) per window |
| `models/moby_narw.pt` | the 5 fold models + normalization stats + feature spec + report |
| `models/moby_narw.json` | per-fold and ensemble metrics, test indices, config |
| `models/moby_narw.onnx` | the ensemble as one graph: inputs `x2d` (B,103,126), `x1d` (B,7,126) → `p_whale` (B,) |

```python
import numpy as np, torch
from train import load_ensemble
from features import clip_features
ens = load_ensemble("models/moby_narw.pt")
x2, x1 = clip_features(audio_2khz_4000_samples)
p_whale = ens(torch.from_numpy(x2)[None], torch.from_numpy(x1)[None]).item()
```

## Notes
- The Kaggle test set (54,504 unlabeled clips) is untouched; all numbers are on a 4,500-clip held-out slice of the labeled set.
- Kaggle gives no buoy / time metadata, so the split is by clip. The poster's 0.977 AUROC was measured the same way.
- Chroma is musically meaningless on whale audio and spectral contrast needs `fmin=15, n_bands=6` at 2 kHz to stay below
  Nyquist; both are kept to match the poster's 11-feature front end. Dropping chroma is a cheap ablation to try.
- For the buoy the whole ensemble runs as one ONNX graph; if latency matters, a single fold model is ~5x cheaper at ~0.5-1 AUROC point.
