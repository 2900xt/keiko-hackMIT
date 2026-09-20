#!/usr/bin/env python3
"""Two-branch features for the Moby right-whale detector (the ISEF poster pipeline, Figure 6).

    python3 features.py                 # ~/Downloads/whale-detection-challenge.zip -> ../dataset/features/moby_narw.npz
    python3 features.py --limit 500     # smoke test

Every 2 s / 2 kHz Kaggle clip becomes:
    X2  float16 (103, 126)   2D branch: rows = [log-mel 64 | MFCC 20 | chroma 12 | spectral contrast 7], 126 frames (16 ms)
    X1  float16 (7, 126)     1D branch: log-RMS, spectral centroid, bandwidth, rolloff, flatness, zero-crossing rate, f0 (YIN)
    y   int8                 1 = right-whale upcall, 0 = noise            row i is Kaggle clip train{i+1}.aiff

Raw feature values are stored; per-row z-scoring happens inside the model (see train.py), so predict.py can feed
clip_features() output straight in. Requires librosa, soundfile, numpy.
"""
import argparse, io, os, pathlib, sys, time, warnings, zipfile
from concurrent.futures import ProcessPoolExecutor

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "dataset" / "scripts"))
from cornell_kaggle_to_tensor import DEFAULT_ZIP, inner_zip, labels          # noqa: E402

DEFAULT_OUT = HERE.parent / "dataset" / "features" / "moby_narw.npz"
SR, CLIP_S, N_FFT, HOP = 2000, 2.0, 512, 32
N_SAMPLES = int(SR * CLIP_S)
T = N_SAMPLES // HOP + 1                                                  # 126 frames
ROWS_2D = {"logmel": 64, "mfcc": 20, "chroma": 12, "contrast": 7}         # 103 rows
NAMES_1D = ["log_rms", "centroid", "bandwidth", "rolloff", "flatness", "zcr", "f0_yin"]
warnings.filterwarnings("ignore")


def clip_features(audio: np.ndarray):
    """(4000,) float32 @ 2 kHz -> (X2 (103, 126), X1 (7, 126)) float32."""
    import librosa
    a = np.pad(audio, (0, max(0, N_SAMPLES - len(audio))))[:N_SAMPLES].astype(np.float32)
    S = np.abs(librosa.stft(a, n_fft=N_FFT, hop_length=HOP)) ** 2; M = np.sqrt(S)
    logmel = librosa.power_to_db(librosa.feature.melspectrogram(S=S, sr=SR, n_mels=64, fmin=20, fmax=SR / 2), ref=1.0, top_db=None)
    x2 = np.concatenate([logmel,
                         librosa.feature.mfcc(S=logmel, n_mfcc=20),
                         librosa.feature.chroma_stft(S=S, sr=SR, n_fft=N_FFT),
                         librosa.feature.spectral_contrast(S=M, sr=SR, n_fft=N_FFT, fmin=15, n_bands=6)])   # 15*2^6 < Nyquist
    x1 = np.concatenate([np.log(librosa.feature.rms(S=M, frame_length=N_FFT) + 1e-8),
                         librosa.feature.spectral_centroid(S=M, sr=SR),
                         librosa.feature.spectral_bandwidth(S=M, sr=SR),
                         librosa.feature.spectral_rolloff(S=M, sr=SR),
                         librosa.feature.spectral_flatness(S=M),
                         librosa.feature.zero_crossing_rate(a, frame_length=N_FFT, hop_length=HOP),
                         librosa.yin(a, fmin=40, fmax=500, sr=SR, frame_length=N_FFT, hop_length=HOP)[None]])
    assert x2.shape == (sum(ROWS_2D.values()), T) and x1.shape == (len(NAMES_1D), T), (x2.shape, x1.shape)
    return x2.astype(np.float32), x1.astype(np.float32)


_zip = None
def _init(path):
    global _zip
    _zip = zipfile.ZipFile(path)


def _chunk(idx):
    import soundfile as sf
    X2 = np.empty((len(idx), sum(ROWS_2D.values()), T), np.float16); X1 = np.empty((len(idx), len(NAMES_1D), T), np.float16)
    for k, i in enumerate(idx):
        audio, sr = sf.read(io.BytesIO(_zip.read(f"data/train/train{i + 1}.aiff")), dtype="float32")
        assert sr == SR
        X2[k], X1[k] = clip_features(audio)
    return X2, X1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", type=pathlib.Path, default=DEFAULT_ZIP)
    ap.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    a = ap.parse_args()
    if not a.zip.exists():
        sys.exit(f"not found: {a.zip}")
    inner = inner_zip(a.zip)
    y = labels(inner)[: a.limit or None]
    n, t0 = len(y), time.time()
    chunks = np.array_split(np.arange(n), max(1, n // 100))
    X2, X1 = [], []
    with ProcessPoolExecutor(a.workers, initializer=_init, initargs=(str(inner),)) as ex:
        for j, (b2, b1) in enumerate(ex.map(_chunk, chunks)):
            X2.append(b2); X1.append(b1)
            print(f"\r{sum(len(b) for b in X1)}/{n} clips  {time.time() - t0:.0f} s", end="", flush=True)
    print()
    X2, X1 = np.concatenate(X2), np.concatenate(X1)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez(a.out, X2=X2, X1=X1, y=y)
    print(f"{a.out}: X2 {X2.shape}  X1 {X1.shape}  y {y.shape}  whale={int(y.sum())}  {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
