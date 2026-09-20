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
python train.py                        # 12 epochs, batch 128, ~25 s/epoch on an M-series GPU (mps); CPU is ~5x slower
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

## Results (v1, 12 epochs, seed 0)

| | window macro-F1 | window acc | clip-level macro-F1 |
|---|---|---|---|
| val (best epoch 8) | 0.51 | 0.73 | 0.45 |
| test | 0.41 | 0.74 | 0.41 |

Per-class test F1: minke 0.99, N. Atlantic right whale 0.99, fin 0.93, sperm 0.90, pantropical spotted dolphin 0.84,
killer whale 0.60, humpback 0.57, spinner 0.53, long-finned pilot 0.44, bowhead 0.43, common dolphin 0.39; the small
dolphin classes (beluga, Risso's, white-beaked, bottlenose, striped, white-sided, false killer, short-finned pilot) are
near zero — too few tapes. Full report in `runs/whale_cnn/test_metrics.json` after training.

Saved model: `models/whale_cnn_v1.pt` (+ `.onnx`, `.json`) — committed, 4.8 MB.

## Files

| Path | What |
|---|---|
| `train.py` | everything: data, model, training loop, evaluation, export |
| `predict.py` | `python predict.py file.wav` — species for any WAV (does the feature extraction itself) |
| `whale_cnn.ipynb` | the same pipeline as a step-by-step notebook (kernel "Python 3 (marine)") |
| `models/whale_cnn_v1.pt` | reload-able checkpoint: weights + classes + arch + feature spec + metrics |
| `models/whale_cnn_v1.onnx` | same network for ONNX Runtime (input `log_mel` (B,1,128,301) → `logits`) |
| `runs/<name>/best.pt` | checkpoint (`model`, `classes`, `config`) |
| `runs/<name>/history.json` | per-epoch loss / val metrics |
| `runs/<name>/test_metrics.json`, `test_confusion.csv` | final test report |

## Using the model

```python
import torch, numpy as np
from train import WhaleCNN
ck = torch.load("runs/whale_cnn/best.pt", map_location="cpu")
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
- Expect low scores on species with < 300 training windows (beluga, white-beaked dolphin, bottlenose, Risso's).
