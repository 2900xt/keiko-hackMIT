#!/usr/bin/env python3
"""Kaggle Whale Detection Challenge zip -> one grayscale spectrogram tensor file.

    python3 scripts/cornell_kaggle_to_tensor.py                  # ~/Downloads/whale-detection-challenge.zip
    python3 scripts/cornell_kaggle_to_tensor.py --limit 500      # smoke test

Writes features/cornell_2k_spec.npz with two arrays:
    X   uint8 (30000, 129, 251)   log-power STFT of each 2 s clip, min-max scaled to 0..255 (one channel)
    y   int8  (30000,)            1 = right-whale upcall, 0 = noise
Row i is Kaggle clip train{i+1}.aiff. STFT: 2 kHz, n_fft 256, hop 16 -> 7.8 Hz bins x 8 ms frames, 0-1000 Hz.

    d = np.load("features/cornell_2k_spec.npz"); X, y = d["X"], d["y"]
    x = torch.from_numpy(X[idx].astype(np.float32) / 255)[:, None]     # (B, 1, 129, 251)
"""
import argparse, io, os, pathlib, sys, time, zipfile
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import scipy.signal
import soundfile as sf

HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_ZIP = pathlib.Path.home() / "Downloads" / "whale-detection-challenge.zip"
DEFAULT_OUT = HERE.parent / "features" / "cornell_2k_spec.npz"
CACHE = pathlib.Path.home() / ".cache" / "whale-detection-challenge"
SR, N_FFT, HOP = 2000, 256, 16
SHAPE = (N_FFT // 2 + 1, 4000 // HOP + 1)                        # (129, 251) for a 4000-sample clip


def inner_zip(outer: pathlib.Path) -> pathlib.Path:
    """Unpack the nested whale_data.zip once (reading AIFFs through the deflated nested stream is ~10x slower)."""
    inner = CACHE / "whale_data.zip"
    if not inner.exists():
        print(f"unpacking whale_data.zip -> {inner}")
        CACHE.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(outer) as z:
            z.extract("whale_data.zip", CACHE)
    return inner


def labels(inner: pathlib.Path) -> np.ndarray:
    with zipfile.ZipFile(inner) as z:
        rows = z.read("data/train.csv").decode().splitlines()[1:]          # clip_name,label
    names, y = zip(*(r.split(",") for r in rows))
    assert names == tuple(f"train{i + 1}.aiff" for i in range(len(names))), "train.csv is not in train1..N order"
    return np.array(y, np.int8)


def spectrogram(audio: np.ndarray) -> np.ndarray:
    _, _, Z = scipy.signal.stft(audio, fs=SR, nperseg=N_FFT, noverlap=N_FFT - HOP)
    S = np.log10(np.abs(Z) ** 2 + 1e-10)
    S = (S - S.min()) / (S.max() - S.min() + 1e-12)
    return (S * 255).round().astype(np.uint8)


_zip = None
def _init(path):
    global _zip
    _zip = zipfile.ZipFile(path)


def _chunk(idx):
    out = np.empty((len(idx), *SHAPE), np.uint8)
    for k, i in enumerate(idx):
        audio, _ = sf.read(io.BytesIO(_zip.read(f"data/train/train{i + 1}.aiff")), dtype="float32")
        out[k] = spectrogram(audio)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", type=pathlib.Path, default=DEFAULT_ZIP)
    ap.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    if not a.zip.exists():
        sys.exit(f"not found: {a.zip}")
    inner = inner_zip(a.zip)
    y = labels(inner)[: a.limit or None]
    n, t0 = len(y), time.time()
    chunks = np.array_split(np.arange(n), max(1, n // 250))
    with ProcessPoolExecutor(os.cpu_count(), initializer=_init, initargs=(str(inner),)) as ex:
        X = np.concatenate(list(ex.map(_chunk, chunks)))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez(a.out, X=X, y=y)
    print(f"{a.out}: X {X.shape} uint8, y {y.shape}, whale={int(y.sum())} noise={int((y == 0).sum())}, {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
