#!/usr/bin/env python3
"""Cornell/Kaggle Whale Detection Challenge -> one grayscale spectrogram tensor.

Replaces the old TFRecord notebook (glob over /kaggle/input, a separate 255x255 RGB PNG dataset, PNG bytes inside
TFRecords). One zip in, one tensor out:

    python cornell_kaggle_to_tensor.py                                   # ~/Downloads/whale-detection-challenge.zip
    python cornell_kaggle_to_tensor.py --zip path/to/whale-detection-challenge.zip --out ../features/cornell_2k_spec
    python cornell_kaggle_to_tensor.py --limit 500                       # quick smoke test

Input:  whale-detection-challenge.zip  (Kaggle download; contains whale_data.zip -> data/train.csv + data/train/*.aiff,
        30,000 clips, mono 16-bit, 2 kHz, 2 s = 4000 samples)
Output (--out dir):
    X.npy           uint8  (N, 129, 251)   grayscale log-power spectrogram per clip, min-max scaled to 0..255 like an
                                           image. Single channel: the old pipeline stored 3 identical RGB planes.
    y.npy           int8   (N,)            1 = right-whale upcall, 0 = noise
    manifest.csv    clip_name,label,index   row i <-> X[i]
    meta.json       the STFT config, shapes, class counts

Spectrogram: STFT n_fft 256 (7.8 Hz bins, 0-1000 Hz), hop 16 (8 ms) -> (129 freq, 251 frames), log10 power.
Right-whale upcalls sweep ~50-250 Hz over ~1 s, so this keeps them ~15-30 bins tall and ~120 frames wide.

Loading it back:

    X = np.load("X.npy", mmap_mode="r"); y = np.load("y.npy")
    x = torch.from_numpy(X[idx].astype(np.float32) / 255.0)[:, None]          # (B, 1, 129, 251)
    # or tf.data:  tf.data.Dataset.from_tensor_slices((X[..., None], y)).map(lambda a, b: (tf.cast(a, tf.float32) / 255., b))
"""
import argparse, csv, io, json, os, pathlib, sys, time, zipfile
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import scipy.signal
import soundfile as sf

HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_ZIP = pathlib.Path.home() / "Downloads" / "whale-detection-challenge.zip"
DEFAULT_OUT = HERE.parent / "features" / "cornell_2k_spec"
INNER_ZIP = "whale_data.zip"
SR, N_SAMPLES = 2000, 4000
N_FFT, HOP = 256, 16
N_FREQ, N_FRAMES = N_FFT // 2 + 1, N_SAMPLES // HOP + 1          # 129, 251


def unpack_inner_zip(outer_zip: pathlib.Path, cache_dir: pathlib.Path) -> pathlib.Path:
    """The Kaggle download nests whale_data.zip (deflated) inside the outer zip. Extract it once to cache_dir;
    reading AIFFs through the nested stream is ~10x slower because every seek re-inflates from the start."""
    inner = cache_dir / INNER_ZIP
    if inner.exists():
        return inner
    print(f"extracting {INNER_ZIP} from {outer_zip} -> {inner} (once, ~550 MB)")
    cache_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(outer_zip) as z:
        z.extract(INNER_ZIP, cache_dir)
    return inner


def read_labels(inner_zip: pathlib.Path):
    """data/train.csv -> [(clip_name, label)], clip_name without the .aiff suffix (train1, train2, ...)."""
    with zipfile.ZipFile(inner_zip) as z, z.open("data/train.csv") as f:
        rows = list(csv.DictReader(io.TextIOWrapper(f, "utf-8")))
    return [(r["clip_name"].removesuffix(".aiff"), int(r["label"])) for r in rows]


def spectrogram(audio: np.ndarray) -> np.ndarray:
    """(4000,) float audio -> (129, 251) uint8 grayscale log-power spectrogram."""
    if len(audio) != N_SAMPLES:                                     # every clip is 4000 samples; guard anyway
        audio = np.pad(audio, (0, max(0, N_SAMPLES - len(audio))))[:N_SAMPLES]
    _, _, Z = scipy.signal.stft(audio, fs=SR, nperseg=N_FFT, noverlap=N_FFT - HOP, window="hann", boundary="zeros", padded=True)
    S = np.log10(np.abs(Z) ** 2 + 1e-10)                             # (129, 251) log power, low freq at row 0
    lo, hi = S.min(), S.max()
    return ((S - lo) / (hi - lo + 1e-12) * 255).round().astype(np.uint8)


_Z = None
def _worker_init(inner_zip):
    global _Z
    _Z = zipfile.ZipFile(inner_zip)                                  # one handle per worker process


def _worker(names):
    out = np.empty((len(names), N_FREQ, N_FRAMES), np.uint8)
    for i, name in enumerate(names):
        audio, sr = sf.read(io.BytesIO(_Z.read(f"data/train/{name}.aiff")), dtype="float32")
        assert sr == SR, f"{name}: {sr} Hz"
        out[i] = spectrogram(audio)
    return out


def build(inner_zip, labels, out_dir, workers, chunk=250):
    n = len(labels)
    out_dir.mkdir(parents=True, exist_ok=True)
    X = np.lib.format.open_memmap(out_dir / "X.npy", mode="w+", dtype=np.uint8, shape=(n, N_FREQ, N_FRAMES))
    chunks = [[nm for nm, _ in labels[i:i + chunk]] for i in range(0, n, chunk)]
    t0 = time.time()
    with ProcessPoolExecutor(workers, initializer=_worker_init, initargs=(str(inner_zip),)) as ex:
        for j, block in enumerate(ex.map(_worker, chunks)):
            X[j * chunk:j * chunk + len(block)] = block
            done = min(n, (j + 1) * chunk)
            print(f"\r{done}/{n} clips  {done / (time.time() - t0):.0f} clips/s", end="", flush=True)
    print()
    X.flush()
    y = np.array([lab for _, lab in labels], np.int8)
    np.save(out_dir / "y.npy", y)
    with open(out_dir / "manifest.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["clip_name", "label", "index"])
        w.writerows((nm, lab, i) for i, (nm, lab) in enumerate(labels))
    meta = {"source": "Cornell/Marinexplore Whale Detection Challenge (Kaggle 2013), data/train", "n": n,
            "X": {"file": "X.npy", "dtype": "uint8", "shape": [n, N_FREQ, N_FRAMES], "axes": ["clip", "freq_bin", "frame"],
                  "scale": "per-clip min-max of log10 power -> 0..255", "channels": 1},
            "y": {"file": "y.npy", "dtype": "int8", "1": "right whale upcall", "0": "noise"},
            "stft": {"sr": SR, "n_fft": N_FFT, "hop": HOP, "window": "hann", "freq_res_hz": SR / N_FFT, "frame_ms": HOP / SR * 1000,
                     "fmax_hz": SR / 2},
            "class_counts": {"0": int((y == 0).sum()), "1": int((y == 1).sum())}}
    json.dump(meta, open(out_dir / "meta.json", "w"), indent=1)
    return X, y, meta


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--zip", type=pathlib.Path, default=DEFAULT_ZIP, help="Kaggle whale-detection-challenge.zip")
    ap.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT, help="output directory (X.npy, y.npy, manifest.csv, meta.json)")
    ap.add_argument("--cache", type=pathlib.Path, help="where to unpack the inner whale_data.zip (default: --out)")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--limit", type=int, default=0, help="debug: only the first N clips")
    a = ap.parse_args()
    if not a.zip.exists():
        sys.exit(f"zip not found: {a.zip}")
    inner = unpack_inner_zip(a.zip, a.cache or a.out)
    labels = read_labels(inner)
    if a.limit:
        labels = labels[:a.limit]
    print(f"{len(labels)} labeled clips -> {a.out}")
    X, y, meta = build(inner, labels, a.out, a.workers)
    print(f"X {X.shape} {X.dtype} ({X.nbytes / 1e6:.0f} MB)   y {y.shape}   whale={meta['class_counts']['1']} noise={meta['class_counts']['0']}")


if __name__ == "__main__":
    main()
