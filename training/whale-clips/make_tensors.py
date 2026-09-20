#!/usr/bin/env python3
"""Turn the whale-clips bundle into preprocessed tensors.

Reads <clips>/train.csv + <clips>/train/*.wav (from build_whale_clips.py) and writes
<out>/<name>/:

  windows.npy    float16 memmap, shape (N, n_mels, frames): log-mel spectrogram in dB,
                 per clip referenced to its own peak and clipped to [-80, 0]
  label.npy      int8   (N,)  1 = whale call, 0 = noise            (Kaggle target)
  species.npy    int16  (N,)  index into labels.json["species"]; -1 = noise
  split.npy      uint8  (N,)  0 = train, 1 = test
  manifest.csv   train.csv with a `row` column = index into the arrays
  labels.json    config, shapes, species and site vocabularies

Defaults match the clips (8 kHz, 2 s): n_fft 512, hop 80 (10 ms), 64 mels 10–4000 Hz, so each
window is 64 x 201. Load for training with:

    import numpy as np, json
    X = np.load("windows.npy", mmap_mode="r")          # (N, 64, 201) float16
    y = np.load("label.npy"); sp = np.load("species.npy"); split = np.load("split.npy")
    tr = np.where(split == 0)[0]
    # torch: torch.from_numpy(np.asarray(X[idx], dtype=np.float32)).unsqueeze(1) -> (B, 1, 64, 201)

Usage:
  python3 make_tensors.py --clips ~/Projects/marine-sounds-db/whale-clips --out ~/Projects/marine-sounds-db/features
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from multiprocessing import Pool
from pathlib import Path

import librosa
import numpy as np
import pandas as pd
import soundfile as sf

CFG: dict = {}


def _init(cfg: dict) -> None:
    CFG.update(cfg)
    CFG["mel"] = librosa.filters.mel(sr=cfg["sr"], n_fft=cfg["n_fft"], n_mels=cfg["n_mels"], fmin=cfg["fmin"], fmax=cfg["fmax"])


def featurize(job: tuple[int, str]) -> tuple[int, np.ndarray | None]:
    i, path = job
    try:
        x, sr = sf.read(path, dtype="float32", always_2d=True)
        x = x.mean(axis=1)
        if sr != CFG["sr"]:
            x = librosa.resample(x, orig_sr=sr, target_sr=CFG["sr"])
        n = CFG["sr"] * CFG["win_s"]
        x = x[:n] if len(x) >= n else np.pad(x, (0, n - len(x)))
        S = np.abs(librosa.stft(x, n_fft=CFG["n_fft"], hop_length=CFG["hop"], center=True)) ** 2
        M = CFG["mel"] @ S
        db = librosa.power_to_db(M, ref=np.max, top_db=80.0)
        return i, db[:, : CFG["frames"]].astype(np.float16)
    except Exception as e:  # unreadable clip: leave zeros, report
        print(f"  skip {path}: {e}", file=sys.stderr)
        return i, None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clips", default="~/Projects/marine-sounds-db/whale-clips")
    ap.add_argument("--out", default="~/Projects/marine-sounds-db/features")
    ap.add_argument("--name", default="whaleclips_8k_mel64_2s")
    ap.add_argument("--sr", type=int, default=8000)
    ap.add_argument("--win-s", type=int, default=2)
    ap.add_argument("--n-fft", type=int, default=512)
    ap.add_argument("--hop", type=int, default=80)
    ap.add_argument("--n-mels", type=int, default=64)
    ap.add_argument("--fmin", type=float, default=10.0)
    ap.add_argument("--fmax", type=float, default=4000.0)
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    clips, out = Path(a.clips).expanduser(), Path(a.out).expanduser() / a.name
    out.mkdir(parents=True, exist_ok=True)

    t = pd.read_csv(clips / "train.csv", low_memory=False)
    if a.limit:
        t = t.head(a.limit)
    t = t.reset_index(drop=True)
    t.insert(0, "row", np.arange(len(t)))
    N = len(t)
    frames = a.sr * a.win_s // a.hop + 1
    cfg = dict(sr=a.sr, win_s=a.win_s, n_fft=a.n_fft, hop=a.hop, n_mels=a.n_mels, fmin=a.fmin, fmax=a.fmax, frames=frames)
    print(f"{N:,} clips -> windows ({N}, {a.n_mels}, {frames}) float16", file=sys.stderr)

    species = sorted(s for s in t.species.dropna().unique() if s)
    sp_id = {s: i for i, s in enumerate(species)}
    sites = sorted(t.site_id.dropna().unique())

    X = np.lib.format.open_memmap(out / "windows.npy", mode="w+", dtype=np.float16, shape=(N, a.n_mels, frames))
    bad = []
    jobs = [(i, str(clips / "train" / n)) for i, n in enumerate(t.clip_name)]
    with Pool(a.workers, initializer=_init, initargs=(cfg,)) as pool:
        for k, (i, f) in enumerate(pool.imap_unordered(featurize, jobs, chunksize=256), 1):
            if f is None:
                bad.append(i)
            else:
                X[i] = f
            if k % 20000 == 0:
                print(f"  {k:,}/{N:,}", file=sys.stderr)
    X.flush()

    np.save(out / "label.npy", t.label.astype(np.int8).to_numpy())
    np.save(out / "species.npy", t.species.map(sp_id).fillna(-1).astype(np.int16).to_numpy())
    np.save(out / "split.npy", (t.split == "test").astype(np.uint8).to_numpy())
    t.to_csv(out / "manifest.csv", index=False)
    with open(out / "labels.json", "w") as f:
        json.dump({"config": {**cfg, "name": a.name}, "n": N, "shape": [N, a.n_mels, frames], "species": species, "sites": sites,
                   "label": {"0": "noise", "1": "whale"}, "split": {"0": "train", "1": "test"}, "bad_rows": bad,
                   "counts": {"whale": int(t.label.sum()), "noise": int((t.label == 0).sum()), "train": int((t.split == "train").sum()), "test": int((t.split == "test").sum())}}, f, indent=1)
    print(f"wrote {out}  bad rows: {len(bad)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
