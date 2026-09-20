#!/usr/bin/env python3
"""Labeled Charles clips -> the same log-mel tensor format the whale CNN was pretrained on (v2_32k_mel128_3s).

    python data/charles_features.py                      # data/charles_clips.csv -> data/charles_v2/
    python data/charles_features.py --split-by group     # default; sessions never straddle splits

Reuses the exact featurize() from ../dataset/scripts/extract_features_v2.py (32 kHz, 3 s windows, 128 mels, per-recording
z-score) so a checkpoint from whale_cnn/train.py can be fine-tuned without any input-side change. Writes windows.npy
(N, 128, 301) float16, manifest.csv (window_id, clip_id, label, hierarchy, group, split, clip_offset_s), labels.json.
"""
import argparse, json, pathlib, sys
import numpy as np, pandas as pd

HERE = pathlib.Path(__file__).resolve().parent; ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "training" / "dataset" / "scripts"))
import extract_features_v2 as fx  # noqa: E402

CFG = dict(sr=32000, win_s=3.0, n_fft=1024, hop=320, n_mels=128, fmin=10.0, fmax=16000.0, max_win=40)

def assign_splits(df, frac=(0.7, 0.15, 0.15), seed=0):
    """Whole recording sessions go to one split; smallest class decides first so every class has test data."""
    rng = np.random.default_rng(seed); split = {}
    for label in df.groupby("label").size().sort_values().index:
        groups = [g for g in df[df.label == label].group.unique() if g not in split]; rng.shuffle(groups)
        n = len(groups); n_val, n_test = max(1, int(n * frac[1])) if n >= 3 else 0, max(1, int(n * frac[2])) if n >= 3 else 0
        for i, g in enumerate(groups): split[g] = "test" if i < n_test else "val" if i < n_test + n_val else "train"
    return df.group.map(split)

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clips", type=pathlib.Path, default=HERE / "charles_clips.csv")
    ap.add_argument("--labels", type=pathlib.Path, default=HERE.parent / "configs" / "charles_labels.csv")
    ap.add_argument("--out", type=pathlib.Path, default=HERE / "charles_v2")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    vocab = pd.read_csv(a.labels, comment="#"); hier = dict(zip(vocab.label, vocab.hierarchy))
    df = pd.read_csv(a.clips); df = df[df.label.fillna("") != ""].copy()
    bad = set(df.label) - set(vocab.label)
    if bad: sys.exit(f"labels not in {a.labels.name}: {bad}")
    if df.empty: sys.exit(f"no labeled rows in {a.clips}; fill in the label column first")
    df["split"] = assign_splits(df, seed=a.seed)
    fx.ROOT = ROOT; fx._init(CFG)
    feats, rows = [], []
    for r in df.itertuples():
        cid, out, starts = fx.featurize((r.clip_id, r.file_path))
        if out is None: print("skip", cid, starts, file=sys.stderr); continue
        feats.append(out)
        rows += [dict(window_id=None, clip_id=cid, label=r.label, hierarchy=hier[r.label], group=r.group, split=r.split,
                      clip_offset_s=round(s, 2), n_windows_in_clip=len(starts)) for s in starts]
    X = np.concatenate(feats); m = pd.DataFrame(rows); m["window_id"] = range(len(m))
    a.out.mkdir(parents=True, exist_ok=True); np.save(a.out / "windows.npy", X); m.to_csv(a.out / "manifest.csv", index=False)
    labels = sorted(m.label.unique())
    json.dump({"config": CFG | {"name": a.out.name, "seed": a.seed}, "n_windows": len(m), "n_clips": int(m.clip_id.nunique()), "shape": list(X.shape),
               "label_id": {l: i for i, l in enumerate(labels)}, "hierarchy": hier,
               "windows_per_label_per_split": m.groupby(["label", "split"]).size().unstack(fill_value=0).to_dict("index")},
              open(a.out / "labels.json", "w"), indent=1)
    print(f"{X.shape} windows from {m.clip_id.nunique()} clips -> {a.out}")
    print(m.groupby(["label", "split"]).size().unstack(fill_value=0).to_string())

if __name__ == "__main__": main()
