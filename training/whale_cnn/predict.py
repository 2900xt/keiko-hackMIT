#!/usr/bin/env python3
"""Classify whale species in a WAV file with a saved checkpoint.

    python predict.py some_recording.wav                       # uses models/whale_cnn_v1.pt
    python predict.py a.wav b.wav --model runs/whale_cnn/best.pt --top 3

Does the same preprocessing as ../dataset/scripts/extract_whale_features.py (mono, resample, 3 s windows with 50% overlap,
128-bin log-mel, per-window z-score), runs every window through the CNN, and prints the per-window top classes plus the
clip-level result (mean of softmax over windows).
"""
import argparse, pathlib, json, sys
import numpy as np, torch, soundfile as sf, librosa
from train import WhaleCNN

HERE = pathlib.Path(__file__).resolve().parent

def load_model(path):
    ck = torch.load(path, map_location="cpu")
    arch = ck.get("arch", {}); classes = ck["classes"]
    model = WhaleCNN(len(classes), width=arch.get("width", 32)); model.load_state_dict(ck["model"]); model.eval()
    spec = ck.get("feature_spec") or {"sr": 32000, "win_s": 3.0, "n_fft": 1024, "hop": 320, "n_mels": 128, "fmin": 10.0, "fmax": 16000.0}
    return model, classes, spec

def windows_from_wav(path, spec, max_win=None):
    y, sr0 = sf.read(str(path), dtype="float32", always_2d=True); y = y.mean(1)
    sr = int(spec["sr"])
    if sr0 != sr: y = librosa.resample(y, orig_sr=sr0, target_sr=sr, res_type="soxr_hq")
    n = int(spec["win_s"] * sr); hop = n // 2
    if len(y) < n: pad = n - len(y); y = np.pad(y, (pad // 2, pad - pad // 2)); starts = [0]
    else: starts = list(range(0, len(y) - n + 1, hop))
    if max_win and len(starts) > max_win: starts = [starts[i] for i in np.linspace(0, len(starts) - 1, max_win).round().astype(int)]
    T = 1 + n // int(spec["hop"]); out = np.zeros((len(starts), int(spec["n_mels"]), T), dtype=np.float32)
    for k, s in enumerate(starts):
        m = librosa.feature.melspectrogram(y=y[s:s + n], sr=sr, n_fft=int(spec["n_fft"]), hop_length=int(spec["hop"]),
                                           n_mels=int(spec["n_mels"]), fmin=spec["fmin"], fmax=spec["fmax"], power=2.0)
        x = np.log1p(m); x = (x - x.mean()) / (x.std() + 1e-6); out[k, :, :x.shape[1]] = x[:, :T]
    return out, [s / sr for s in starts]

def decide(p, classes, min_conf=0.5, margin=0.1):
    """Abstain rule: report a whale only if total whale probability beats the no-whale probability by `margin`
    and the top whale class is at least `min_conf`. Otherwise answer 'no_whale'. Models without no_whale classes fall back to argmax."""
    nw = [i for i, c in enumerate(classes) if c.startswith("no_whale")]
    if not nw: i = int(p.argmax()); return classes[i], float(p[i])
    p_no = float(p[nw].sum()); p_whale = 1.0 - p_no
    wi = [i for i in range(len(classes)) if i not in nw]; best = max(wi, key=lambda i: p[i])
    if p_whale - p_no < margin or p[best] < min_conf: return "no_whale", p_no
    return classes[best], float(p[best])

@torch.no_grad()
def classify(model, classes, spec, wav, top=3, min_conf=0.5, margin=0.1):
    X, offsets = windows_from_wav(wav, spec)
    probs = torch.softmax(model(torch.from_numpy(X)[:, None]), dim=1).numpy()
    clip = probs.mean(0); order = np.argsort(-clip)[:top]
    label, conf = decide(clip, classes, min_conf, margin)
    return {"file": str(wav), "n_windows": len(X), "decision": label, "confidence": conf,
            "clip": [{"species": classes[i], "prob": float(clip[i])} for i in order],
            "windows": [dict(zip(("t", "species", "prob"), (float(t), *decide(p, classes, min_conf, margin)))) for t, p in zip(offsets, probs)]}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("wavs", nargs="+", type=pathlib.Path)
    ap.add_argument("--model", type=pathlib.Path, default=HERE / "models" / "whale_cnn_v2.pt")
    ap.add_argument("--top", type=int, default=3)
    ap.add_argument("--json", action="store_true", help="print full JSON incl. per-window results")
    ap.add_argument("--min_conf", type=float, default=0.5, help="abstain unless the top whale class has at least this probability")
    ap.add_argument("--margin", type=float, default=0.1, help="abstain unless P(whale) - P(no_whale) exceeds this")
    a = ap.parse_args()
    model, classes, spec = load_model(a.model)
    for wav in a.wavs:
        r = classify(model, classes, spec, wav, a.top, a.min_conf, a.margin)
        if a.json: print(json.dumps(r, indent=1)); continue
        print(f"{wav.name}  ({r['n_windows']} windows)  -> {r['decision']} ({r['confidence']:.2f})")
        for c in r["clip"]: print(f"   {c['species']:32s} {c['prob']:.2f}")
