# Whale species CNN

A small PyTorch CNN that classifies 3-second log-mel spectrogram windows into whale species, trained on
`../dataset/features/whales_32k_mel128_3s/` (see `../dataset/README.md` for how those tensors are built).

## Setup

```bash
pip install torch numpy pandas scikit-learn onnx librosa soundfile
# make sure ../dataset/features/whales_32k_mel128_3s/windows.npy exists:
#   cd ../dataset && ./fetch_data.sh && python3 scripts/extract_whale_features.py
```

## Train

```bash
python train.py --features ../dataset/features/v2_32k_mel128_3s --epochs 25 --patience 5 --export models/whale_cnn_v2   # v2
python train.py                        # v1 features, 12 epochs, batch 128, ~25 s/epoch on an M-series GPU (mps); CPU is ~5x slower
python train.py --epochs 30 --width 48 # bigger / longer
python train.py --eval runs/whale_cnn/best.pt   # re-evaluate a checkpoint on the test split
```

What the script does:
- Loads the float16 memmap + `manifest.csv`; uses the manifest's **recording-group split** (train/val/test), so no tape or
  session leaks between splits.
- Merges the four species that come from too few tapes to evaluate (melon-headed whale, Clymene, Atlantic spotted,
  Fraser's dolphin) into `other_whale` -> **20 classes**. `--no_merge_rare` keeps all 24.
- Class-balanced sampling (inverse-sqrt frequency), light SpecAugment (one freq mask, one time mask, random gain),
  label smoothing, AdamW + one-cycle LR.
- Model: stem (avg-pool 2 + 5x5 stride-2 conv, 4x downsampling per axis) -> 4 conv blocks (32->64->128->256, each 2x conv3x3 + BN + ReLU + maxpool) -> mean+max global pooling -> dropout -> linear.
  ~1.2 M parameters. Input `(B, 1, 128, 301)`.
- Keeps the checkpoint with the best **val macro-F1**, then reports test macro-F1 / accuracy at window level and at
  **clip level** (majority vote over a clip's windows), plus a per-class report and confusion matrix in `runs/<name>/`.

## Results

### v2 (current: `models/whale_cnn_v2.pt`) — 22 classes incl. two NOT-a-whale classes

Trained on `../dataset/features/v2_32k_mel128_3s/` (built by `../dataset/scripts/extract_features_v2.py` from the v3 database):
species for baleen + non-dolphin toothed whales, **genus** for dolphins, `other_baleen` / `other_toothed`, and `no_whale_noise`
(ambient, vessels, waves, detector negatives) + `no_whale_biophony` (fish, invertebrates, seals, unidentified reef sounds).
Big classes are capped at ~6k windows drawn evenly across up to 147 recording groups; features are z-scored per *recording*.
Training adds random bandwidth masking (so recorder bandwidth can't be used as a cue), mixup, dropout 0.5, early stopping.

| test | v1 | v2 |
|---|---|---|
| window macro-F1 | 0.41 | **0.45** |
| window accuracy | 0.74 | 0.70 |
| clip-level macro-F1 | 0.41 | **0.44** |
| hierarchy accuracy (baleen / toothed / no-whale) | – | 0.87 |
| false-alarm rate on no-whale windows (argmax) | – | 0.36 |
| whale windows called no-whale (argmax) | – | 0.05 |

Per-class test F1 (v2): right whale 0.96, common minke 0.88, Antarctic minke 0.87, fin 0.83, bowhead 0.82, blue 0.80,
killer whale 0.80, `no_whale_noise` 0.70, `Delphinus` 0.65, humpback 0.62, `no_whale_biophony` 0.60, sperm whale 0.57;
dolphin genera other than *Delphinus* (Stenella, Globicephala, Lagenorhynchus, Grampus, Tursiops, Pseudorca) 0.0–0.2 —
3-s log-mel windows don't resolve them and each still comes from one recorder.

v1's 0.99 scores on fin/minke/right whale were a **recorder-bandwidth shortcut** (each came from a single dataset with its own
sample rate); v2 removes it, so those classes drop to the high 0.80s but bowhead, humpback, blue and orca improve because
they now span many recorders (orca: 147 groups from DCLDE 2027).

### Deciding "whale or not" — the abstain rule in `predict.py`

`predict.py` reports a whale only if `P(any whale) − P(no_whale) > --margin` **and** the top whale class has `P ≥ --min_conf`;
otherwise it says `no_whale`. Sweep on the v2 test split (per 3-s window):

| `--min_conf` | `--margin` | false alarms on no-whale | whales missed | species acc on whale windows |
|---|---|---|---|---|
| 0.0 | 0.0 (argmax) | 0.40 | 0.03 | 0.72 |
| 0.5 | 0.1 (default) | 0.25 | 0.22 | 0.65 |
| 0.6 | 0.2 | 0.19 | 0.32 | 0.58 |
| 0.7 | 0.3 | 0.05 | 0.46 | 0.47 |
| 0.8 | 0.4 | 0.02 | 0.61 | 0.36 |

For a buoy, pick the row by how costly a false alarm is, and additionally require the same class in ≥2 consecutive windows
(clip-level averaging in `predict.py` already helps for recordings longer than 3 s).

### v2.1 (negative result, not shipped)
Same as v2 but the no-whale classes sampled 3× more often (`--noise_weight 3`): false alarms 0.36 → 0.29, but whales missed
0.05 → 0.17 and common minke F1 0.88 → 0.36 (its negatives come from the same towed array). Thresholding at inference is the
better lever. Run is in `runs/whale_cnn_v2_1/` if you train locally.

### v1 (`models/whale_cnn_v1.pt`) — 20 classes, no negatives
test window macro-F1 0.41, acc 0.74; see git history for the per-class table.

## Files

| Path | What |
|---|---|
| `train.py` | everything: data, model, training loop, evaluation, export |
| `predict.py` | `python predict.py file.wav` — species for any WAV (does the feature extraction itself) |
| `whale_cnn.ipynb` | the same pipeline as a step-by-step notebook (kernel "Python 3 (marine)") |
| `models/whale_cnn_v2.pt` / `.onnx` / `.json` | current model: weights + classes + arch + feature spec + metrics; ONNX input `log_mel` (B,1,128,301) → `logits` |
| `models/whale_cnn_v1.*` | previous model (no negatives, bandwidth shortcut) |
| `test_model.ipynb` | load a checkpoint, reproduce test metrics, classify WAVs, check ONNX |
| `runs/<name>/best.pt` | checkpoint (`model`, `classes`, `config`) |
| `runs/<name>/history.json` | per-epoch loss / val metrics |
| `runs/<name>/test_metrics.json`, `test_confusion.csv` | final test report |

## Using the model

```python
import torch, numpy as np
from train import WhaleCNN
ck = torch.load("models/whale_cnn_v2.pt", map_location="cpu")
model = WhaleCNN(len(ck["classes"])); model.load_state_dict(ck["model"]); model.eval()
x = torch.from_numpy(np.load("../dataset/features/whales_32k_mel128_3s/windows.npy", mmap_mode="r")[:8].astype("float32"))[:, None]
print([ck["classes"][i] for i in model(x).argmax(1)])
```

To run on new audio, produce windows exactly as `extract_whale_features.py` does (mono, 32 kHz, 3 s, 128 mel 10 Hz-16 kHz,
n_fft 1024, hop 320, log1p, per-window z-score) and feed them in the same way.

## Caveats
- Macro-F1 is the number to watch; accuracy is inflated by right whale, sperm whale and minke.
- Most species come from one recorder (Watkins tapes), so the model partly learns the recorder. Test on your own
  hydrophone recordings before trusting it in the field.
- Dolphin genera and sperm whale are the weak classes; clicks need finer time resolution (try `--hop 160` in the extractor) and
  the dolphins need more recorders. A pretrained bioacoustic backbone (Perch 2.0 / SurfPerch / BEATs) is the next big step.
