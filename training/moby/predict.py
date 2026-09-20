#!/usr/bin/env python3
"""Run the Moby right-whale ensemble on audio files.

    python3 predict.py recording.wav [more.aiff ...]        # any sample rate; resampled to 2 kHz
    python3 predict.py --model models/moby_narw.pt --hop 1.0 --threshold 0.5 clip.wav

Slides a 2 s window (default hop 1 s) over each file, prints P(whale) per window and the file-level max.
"""
import argparse, pathlib
import numpy as np, torch, librosa

from features import SR, N_SAMPLES, clip_features
from train import load_ensemble

HERE = pathlib.Path(__file__).resolve().parent


def windows(path, hop_s):
    audio, _ = librosa.load(path, sr=SR, mono=True)
    hop = int(hop_s * SR)
    starts = list(range(0, max(1, len(audio) - N_SAMPLES + 1), hop)) or [0]
    return [(s / SR, audio[s:s + N_SAMPLES]) for s in starts]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", type=pathlib.Path)
    ap.add_argument("--model", type=pathlib.Path, default=HERE / "models" / "moby_narw.pt")
    ap.add_argument("--hop", type=float, default=1.0, help="window hop in seconds")
    ap.add_argument("--threshold", type=float, default=0.5)
    a = ap.parse_args()
    ens = load_ensemble(a.model)
    for f in a.files:
        ws = windows(f, a.hop)
        feats = [clip_features(w) for _, w in ws]
        x2 = torch.from_numpy(np.stack([f2 for f2, _ in feats])); x1 = torch.from_numpy(np.stack([f1 for _, f1 in feats]))
        with torch.no_grad():
            p = ens(x2, x1).numpy()
        print(f"{f}: {'WHALE' if p.max() >= a.threshold else 'no whale'}  max P(whale) {p.max():.3f}")
        for (t, _), pi in zip(ws, p):
            print(f"  {t:7.1f}s  {pi:.3f} {'*' if pi >= a.threshold else ''}")


if __name__ == "__main__":
    main()
