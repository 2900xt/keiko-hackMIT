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
python3 train.py         # 2-fold ensemble, ~8 min on an M-series GPU (--folds 5 --epochs 20 for the full poster setup)
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

**Training**: 15% of clips are held out as the test set (stratified, seed 0). The other 85% is split into K stratified folds (default 2 for speed; `--folds 5` reproduces the poster);
each fold model trains on the other folds with AdamW + one-cycle LR, class-weighted cross-entropy (sqrt inverse frequency) with
label smoothing, and early-stops on its own fold's AUROC. Augmentation on the GPU batch, train only: Gaussian blur on the
2D stack (p = 0.5), time dilation 0.85-1.15x applied to both branches together, additive gain jitter, one time mask.

## Results

`python3 train.py` (2 folds, 12 epochs, patience 3, seed 0), held-out test = 4,500 clips (1,054 upcalls). Threshold 0.5 for acc / F1.

| | val AUROC | test AUROC | test acc | test F1 |
|---|---|---|---|---|
| fold 0 model | 0.9690 | 0.9733 | 0.924 | 0.843 |
| fold 1 model | 0.9670 | 0.9741 | 0.914 | 0.832 |
| **ensemble (mean softmax)** | – | **0.9766** | 0.923 | 0.846 |

Poster (5-fold, TensorFlow): AUROC 0.977 ± 0.002 with 343,877 parameters; Cornell baseline 0.72. This port lands in the same
place (357,725 parameters per model). A 5-fold / 20-epoch run of fold 0 alone reached 0.979 test AUROC, so
`--folds 5 --epochs 20` buys a few tenths of a point for ~3x the training time.

Sanity check on raw clips: `python3 predict.py train6.aiff train7.aiff train1.aiff train2.aiff` → 0.68, 0.93 (upcalls) vs 0.10, 0.06 (noise).

### Keiko, the final model: Kaggle + Watkins, `models/keiko.pt`

```bash
python3 train.py --features ../dataset/features/moby_narw_watkins.npz --out models/keiko.pt     # 2 folds, ~8 min
```
`moby_narw_watkins.npz` (built by `watkins_features.py` on the `moby-watkins` branch) = the 30,000 Kaggle rows + 3,073 windows of
Watkins baleen-whale cuts whose calls sit under 1 kHz (humpback 1,518, bowhead 957, N. Atlantic right 475, southern right 66, gray 57),
level-matched to Kaggle and all labelled `y = 1` (Watkins has no noise cuts). `train.py` reads its `source` / `group` / `split` arrays:
the test set is the same 4,500 Kaggle clips plus 379 windows from 9 held-out Watkins **tapes**, and the folds are grouped by tape.
Because every negative is a Kaggle clip, the number to watch is **Kaggle-only** AUROC (is it still a whale detector, or an
"analog tape vs MARU buoy" detector?); Watkins rows can only be scored by recall.

| | val AUROC | test AUROC (all) | test AUROC, Kaggle only | recall on held-out Watkins tapes |
|---|---|---|---|---|
| fold 0 model | 0.9759 | 0.9782 | 0.9705 | 1.000 |
| fold 1 model | 0.9757 | 0.9792 | 0.9718 | 1.000 |
| **ensemble** | – | **0.9816** | **0.9750** (acc 0.922) | **1.000** |

Per species on the held-out tapes: Eschrichtius robustus 1.00, Eubalaena australis 1.00, Eubalaena glacialis 1.00, Megaptera novaeangliae 1.00. Kaggle-only AUROC moved 0.9766 → 0.9750, i.e. adding
Watkins cost nothing on buoy data while the model now fires on humpback, bowhead, gray and right whales from other recorders.
The perfect Watkins recall is partly the tape cue (no Watkins negatives exist to punish it), so treat it as "does not miss",
not as a false-alarm rate; the Kaggle-only accuracy is the false-alarm number.

## Files

| Path | What |
|---|---|
| `features.py` | Kaggle zip → `moby_narw.npz` (`X2` (N,103,126), `X1` (N,7,126), `y`); `clip_features(audio)` is reused by `predict.py` |
| `train.py` | model (`Moby`, `CBAM`, `Ensemble`), K-fold training, evaluation, export; `load_ensemble(path)` |
| `predict.py` | slide 2 s windows over any audio file, print P(whale) per window |
| `models/moby_narw.pt` | the fold models + normalization stats + feature spec + report |
| `models/moby_narw.json` | per-fold and ensemble metrics, test indices, config |
| `models/moby_narw.onnx` | the ensemble as one graph: inputs `x2d` (B,103,126), `x1d` (B,7,126) → `p_whale` (B,) |
| `models/keiko.{pt,json,onnx}` | **the final model**: same format, trained on Kaggle + Watkins (see above); `predict.py` default |

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
