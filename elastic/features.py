"""What goes into an Elasticsearch doc besides the label: cheap spectral descriptors of a window, and the whale
CNN's 512-d penultimate activations as the embedding for kNN "sounds like this".

Both are pure functions so the pipeline, the backfill and the tests share them. numpy only, torch imported lazily.
"""
import numpy as np


def audio_features(y, fs):
    """Spectral descriptors of one window (float samples in ±1 at `fs`): level, peak, centroid, bandwidth, flatness.

    These are what the ML anomaly job watches (noise floor drifting, energy in an unexpected band) and what the
    dashboard plots against the classifier, so they are computed on the raw window, before any resampling."""
    y = np.asarray(y, dtype=np.float32)
    if len(y) < 16:
        return {"rms_db": -120.0, "peak_hz": 0.0, "centroid_hz": 0.0, "bandwidth_hz": 0.0, "flatness": 0.0}
    rms = float(np.sqrt(np.mean(y * y)) + 1e-12)
    spec = np.abs(np.fft.rfft(y * np.hanning(len(y)))) ** 2
    freqs = np.fft.rfftfreq(len(y), d=1.0 / fs)
    spec[0] = 0.0                                       # DC is removed upstream; do not let residue win the peak
    total = float(spec.sum()) + 1e-12
    centroid = float((freqs * spec).sum() / total)
    bandwidth = float(np.sqrt(((freqs - centroid) ** 2 * spec).sum() / total))
    nz = spec[1:] + 1e-20
    flatness = float(np.exp(np.mean(np.log(nz))) / np.mean(nz))   # 1 = white noise, ->0 = a tone
    return {"rms_db": round(20 * np.log10(rms), 1), "peak_hz": round(float(freqs[int(spec.argmax())]), 1),
            "centroid_hz": round(centroid, 1), "bandwidth_hz": round(bandwidth, 1), "flatness": round(flatness, 3)}


def logits_and_embedding(model, x):
    """Run WhaleCNN's forward pass but keep the pooled 512-d vector its classifier head sees.

    x: (B, 1, n_mels, T) tensor. Returns (logits (B, n_classes), embedding (B, 512)). Mirrors train.WhaleCNN.forward."""
    import torch
    with torch.no_grad():
        h = model.features(model.stem(x))
        h = torch.cat([h.mean(dim=(2, 3)), h.amax(dim=(2, 3))], dim=1)
        return model.head(h), h


def unit(v):
    """L2-normalise for cosine kNN; a zero vector stays zero."""
    v = np.asarray(v, dtype=np.float32)
    n = float(np.linalg.norm(v))
    return (v / n if n > 0 else v).tolist()


def mean_embedding(embs):
    """One vector for an event: the mean of its windows' embeddings, normalised."""
    if not embs:
        return None
    return unit(np.mean(np.asarray(embs, dtype=np.float32), axis=0))
