#!/usr/bin/env python3
"""Simple CNN whale-species classifier on the log-mel windows in training/dataset/features/.

    python train.py                       # train with defaults (~20-30 s/epoch on Apple M-series GPU)
    python train.py --epochs 20 --batch 128
    python train.py --eval runs/best.pt   # evaluate a checkpoint on the test split

Reads windows.npy (N, 128, 301) float16 + manifest.csv, trains a 4-block CNN with class-balanced sampling and light
SpecAugment, tracks macro-F1 on val, saves runs/<name>/best.pt, and writes test-set metrics + confusion matrix.
"""
import argparse, json, os, pathlib, time, collections
import numpy as np, pandas as pd, torch, torch.nn as nn, torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader, WeightedRandomSampler
from sklearn.metrics import f1_score, classification_report, confusion_matrix

HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_FEATURES = HERE.parent / "dataset" / "features" / "whales_32k_mel128_3s"
# species whose clips all come from 1-3 tapes; a leak-free split can't evaluate them fairly, so merge into other_whale
RARE_TO_OTHER = {"Peponocephala_electra", "Stenella_clymene", "Stenella_frontalis", "Lagenodelphis_hosei"}

# ----------------------------------------------------------------------------- data
class WindowDataset(Dataset):
    def __init__(self, X, idx, y, augment=False, lowpass=True):
        self.X, self.idx, self.y, self.augment, self.lowpass = X, idx, y, augment, lowpass
    def __len__(self): return len(self.idx)
    def __getitem__(self, i):
        x = torch.from_numpy(np.asarray(self.X[self.idx[i]], dtype=np.float32))[None]   # (1, 128, 301)
        if self.augment:
            # SpecAugment-lite: one frequency mask + one time mask + small random gain
            f0, fw = np.random.randint(0, 128 - 16), np.random.randint(0, 16); x[:, f0:f0 + fw, :] = 0
            t0, tw = np.random.randint(0, 301 - 30), np.random.randint(0, 30); x[:, :, t0:t0 + tw] = 0
            x = x * float(np.exp(np.random.uniform(-0.2, 0.2)))
            if self.lowpass and np.random.rand() < 0.7:
                # random low-pass: zero every mel bin above a random cutoff (bin 30 ~ 1 kHz ... 128 = 16 kHz) and fill with
                # the row's floor noise so "bandwidth of the recorder" stops being a usable feature
                cut = np.random.randint(30, 128); x[:, cut:, :] = x[:, cut:, :].min() if cut < 127 else x[:, cut:, :]
        return x, self.y[i]

def load_data(features, merge_rare=True, in_ram=True):
    X = np.load(features / "windows.npy", mmap_mode="r")
    if in_ram: X = np.ascontiguousarray(X)              # ~3.4 GB float16; random access from disk is 10x slower
    m = pd.read_csv(features / "manifest.csv")
    if merge_rare and "hierarchy" not in m.columns: m.loc[m.label.isin(RARE_TO_OTHER), "label"] = "other_whale"
    classes = sorted(m.label.unique()); cid = {c: i for i, c in enumerate(classes)}
    m["y"] = m.label.map(cid)
    if "hierarchy" not in m.columns: m["hierarchy"] = m.taxon_group.map({"baleen whale": "baleen", "toothed whale": "toothed"}).fillna("no_whale")
    return X, m, classes

# ----------------------------------------------------------------------------- model
class ConvBlock(nn.Module):
    def __init__(self, cin, cout):
        super().__init__()
        self.net = nn.Sequential(nn.Conv2d(cin, cout, 3, padding=1, bias=False), nn.BatchNorm2d(cout), nn.ReLU(inplace=True),
                                 nn.Conv2d(cout, cout, 3, padding=1, bias=False), nn.BatchNorm2d(cout), nn.ReLU(inplace=True),
                                 nn.MaxPool2d(2))
    def forward(self, x): return self.net(x)

class WhaleCNN(nn.Module):
    """Stem downsamples 4x per axis (avg-pool 2 + 5x5 stride-2 conv) so the 4 conv blocks run on 32x75 maps instead of 128x301:
    ~23x fewer FLOPs than the full-resolution version (70 ms vs 1.6 s per batch-128 step on an M-series GPU), same ~1.2M params."""
    def __init__(self, n_classes, width=32, dropout=0.3):
        super().__init__(); w = width
        self.stem = nn.Sequential(nn.AvgPool2d(2), nn.Conv2d(1, w, 5, stride=2, padding=2, bias=False), nn.BatchNorm2d(w), nn.ReLU(inplace=True))
        self.features = nn.Sequential(ConvBlock(w, w), ConvBlock(w, 2 * w), ConvBlock(2 * w, 4 * w), ConvBlock(4 * w, 8 * w))
        self.head = nn.Sequential(nn.Dropout(dropout), nn.Linear(8 * w * 2, n_classes))
    def forward(self, x):                                   # x: (B, 1, 128, 301)
        h = self.features(self.stem(x))                     # (B, 256, 2, 4)
        h = torch.cat([h.mean(dim=(2, 3)), h.amax(dim=(2, 3))], dim=1)   # mean + max pool -> (B, 512)
        return self.head(h)

# ----------------------------------------------------------------------------- train / eval
def device():
    return torch.device("mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu")

@torch.no_grad()
def predict(model, loader, dev):
    model.eval(); ps, ys = [], []
    for x, y in loader:
        ps.append(model(x.to(dev)).argmax(1).cpu()); ys.append(y)
    return torch.cat(ps).numpy(), torch.cat(ys).numpy()

def evaluate(model, X, m, split, classes, dev, batch, out_dir=None, tag="test"):
    idx = m.index[m.split == split].values
    dl = DataLoader(WindowDataset(X, idx, m.y.values[idx]), batch_size=batch, shuffle=False, num_workers=0)
    p, y = predict(model, dl, dev)
    macro = f1_score(y, p, average="macro"); acc = float((p == y).mean())
    present = sorted(set(y) | set(p))
    rep = classification_report(y, p, labels=present, target_names=[classes[i] for i in present], zero_division=0, output_dict=True)
    # clip-level: majority vote over the windows of each clip
    dfc = pd.DataFrame({"clip": m.clip_id.values[idx], "p": p, "y": y}).groupby("clip").agg(p=("p", lambda s: s.mode().iloc[0]), y=("y", "first"))
    clip_macro = f1_score(dfc.y, dfc.p, average="macro")
    hier = dict(zip(m.y.values, m.hierarchy.values)); hp = np.array([hier.get(i, "?") for i in p]); hy = m.hierarchy.values[idx]
    hier_acc = float((hp == hy).mean())
    is_noise = hy == "no_whale"; false_alarm = float((hp[is_noise] != "no_whale").mean()) if is_noise.any() else None
    missed = float((hp[~is_noise] == "no_whale").mean()) if (~is_noise).any() else None
    rep["_hierarchy_acc"] = hier_acc; rep["_false_alarm_rate_on_no_whale"] = false_alarm; rep["_whale_called_no_whale"] = missed
    if out_dir:
        cm = confusion_matrix(y, p, labels=list(range(len(classes))))
        pd.DataFrame(cm, index=classes, columns=classes).to_csv(out_dir / f"{tag}_confusion.csv")
        json.dump({"split": split, "window_macro_f1": macro, "window_acc": acc, "clip_macro_f1": clip_macro, "hierarchy_acc": hier_acc,
                   "false_alarm_rate_on_no_whale": false_alarm, "whale_called_no_whale": missed, "per_class": rep},
                  open(out_dir / f"{tag}_metrics.json", "w"), indent=1)
    return macro, acc, clip_macro, rep

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", type=pathlib.Path, default=DEFAULT_FEATURES)
    ap.add_argument("--name", default="whale_cnn")
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--batch", type=int, default=128)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--width", type=int, default=32)
    ap.add_argument("--steps_per_epoch", type=int, default=250, help="balanced-sampler steps per epoch (250 x 128 = 32k windows)")
    ap.add_argument("--no_merge_rare", action="store_true")
    ap.add_argument("--no_ram", action="store_true", help="keep windows.npy as a disk memmap (slower, low memory)")
    ap.add_argument("--export", default="models/whale_cnn_v1", help="after training, save a reload-able copy + ONNX under this prefix")
    ap.add_argument("--eval", type=pathlib.Path, help="checkpoint to evaluate on test instead of training")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--dropout", type=float, default=0.5)
    ap.add_argument("--mixup", type=float, default=0.2, help="mixup alpha (0 = off)")
    ap.add_argument("--no_lowpass_aug", action="store_true", help="disable the random bandwidth-masking augmentation")
    ap.add_argument("--patience", type=int, default=4, help="early-stop after this many epochs without val improvement")
    ap.add_argument("--noise_weight", type=float, default=1.0, help="multiply sampling weight of no_whale_* classes (>1 = see more negatives)")
    a = ap.parse_args()
    torch.manual_seed(a.seed); np.random.seed(a.seed)
    dev = device(); print("device", dev)
    X, m, classes = load_data(a.features, merge_rare=not a.no_merge_rare, in_ram=not a.no_ram)
    print(f"{len(m)} windows, {len(classes)} classes:", ", ".join(classes))
    out = HERE / "runs" / a.name; out.mkdir(parents=True, exist_ok=True)
    model = WhaleCNN(len(classes), width=a.width, dropout=a.dropout).to(dev)
    print("params", sum(p.numel() for p in model.parameters()) / 1e6, "M")

    if a.eval:
        model.load_state_dict(torch.load(a.eval, map_location=dev)["model"])
        macro, acc, cmacro, rep = evaluate(model, X, m, "test", classes, dev, a.batch, out, "test")
        print(f"TEST window macro-F1 {macro:.3f}  acc {acc:.3f}  clip-level macro-F1 {cmacro:.3f}")
        for c in classes:
            if c in rep: print(f"  {c:32s} f1={rep[c]['f1-score']:.2f} n={int(rep[c]['support'])}")
        return

    tr_idx = m.index[m.split == "train"].values; ytr = m.y.values[tr_idx]
    counts = np.bincount(ytr, minlength=len(classes)); w = 1.0 / np.sqrt(np.maximum(counts, 1))   # sqrt-inverse-frequency balancing
    for i, c in enumerate(classes):
        if c.startswith("no_whale"): w[i] *= a.noise_weight
    sampler = WeightedRandomSampler(torch.as_tensor(w[ytr], dtype=torch.double), num_samples=a.steps_per_epoch * a.batch, replacement=True)
    dl = DataLoader(WindowDataset(X, tr_idx, ytr, augment=True, lowpass=not a.no_lowpass_aug), batch_size=a.batch, sampler=sampler, num_workers=0, drop_last=True)
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=1e-2)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=a.lr, total_steps=a.epochs * a.steps_per_epoch)
    best = -1; hist = []; bad = 0
    for ep in range(1, a.epochs + 1):
        model.train(); t0 = time.time(); tot = 0.0; n = 0
        for x, y in dl:
            x, y = x.to(dev), y.to(dev)
            if a.mixup > 0:
                lam = float(np.random.beta(a.mixup, a.mixup)); perm = torch.randperm(len(y), device=dev)
                logits = model(lam * x + (1 - lam) * x[perm])
                loss = lam * F.cross_entropy(logits, y, label_smoothing=0.05) + (1 - lam) * F.cross_entropy(logits, y[perm], label_smoothing=0.05)
            else:
                loss = F.cross_entropy(model(x), y, label_smoothing=0.05)
            opt.zero_grad(set_to_none=True); loss.backward(); opt.step(); sched.step()
            tot += loss.item() * len(y); n += len(y)
        vmacro, vacc, vclip, vrep = evaluate(model, X, m, "val", classes, dev, a.batch)
        fa = vrep.get("_false_alarm_rate_on_no_whale"); fa_s = f"  false-alarm {fa:.3f}" if fa is not None else ""
        hist.append({"epoch": ep, "train_loss": tot / n, "val_macro_f1": vmacro, "val_acc": vacc, "val_clip_macro_f1": vclip, "val_hier_acc": vrep["_hierarchy_acc"], "val_false_alarm": fa, "sec": time.time() - t0})
        print(f"epoch {ep:2d}  loss {tot/n:.3f}  val macro-F1 {vmacro:.3f}  acc {vacc:.3f}  clip-F1 {vclip:.3f}  hier-acc {vrep['_hierarchy_acc']:.3f}{fa_s}  ({time.time()-t0:.0f}s)", flush=True)
        if vmacro > best:
            best = vmacro; bad = 0; torch.save({"model": model.state_dict(), "classes": classes, "config": vars(a) | {"features": str(a.features)}}, out / "best.pt")
        else:
            bad += 1
            if bad >= a.patience: print(f"early stop at epoch {ep} (no val improvement for {a.patience} epochs)", flush=True); break
    json.dump(hist, open(out / "history.json", "w"), indent=1)
    model.load_state_dict(torch.load(out / "best.pt", map_location=dev)["model"])
    macro, acc, cmacro, rep = evaluate(model, X, m, "test", classes, dev, a.batch, out, "test")
    print(f"\nBEST val macro-F1 {best:.3f} -> TEST window macro-F1 {macro:.3f}  acc {acc:.3f}  clip-level macro-F1 {cmacro:.3f}")
    print(f"  hierarchy (baleen/toothed/no_whale) acc {rep['_hierarchy_acc']:.3f}   false-alarm rate on no-whale windows {rep['_false_alarm_rate_on_no_whale']}   whales called no-whale {rep['_whale_called_no_whale']}")
    for c in classes:
        if c in rep: print(f"  {c:32s} f1={rep[c]['f1-score']:.2f} n={int(rep[c]['support'])}")
    print("saved", out / "best.pt", "and", out / "test_metrics.json")
    if a.export: export_model(model, classes, a, out, HERE / a.export, {"test_window_macro_f1": macro, "test_acc": acc, "test_clip_macro_f1": cmacro})

def export_model(model, classes, a, run_dir, prefix, metrics):
    """Save a self-describing checkpoint (weights + classes + feature config) and an ONNX graph for non-PyTorch runtimes."""
    prefix.parent.mkdir(parents=True, exist_ok=True)
    feat_cfg = json.load(open(a.features / "labels.json"))["config"]
    feature_spec = {k: feat_cfg[k] for k in ("sr", "win_s", "n_fft", "hop", "n_mels", "fmin", "fmax")}
    torch.save({"model": model.state_dict(), "classes": classes, "arch": {"width": a.width, "n_classes": len(classes)},
                "feature_spec": feature_spec, "metrics": metrics, "train_config": {k: str(v) for k, v in vars(a).items()}}, str(prefix) + ".pt")
    model.eval().cpu()
    try:
        torch.onnx.export(model, torch.zeros(1, 1, 128, 301), str(prefix) + ".onnx", input_names=["log_mel"], output_names=["logits"],
                          dynamic_axes={"log_mel": {0: "batch"}, "logits": {0: "batch"}}, opset_version=17, dynamo=False)
        onnx_ok = True
    except Exception as e:
        onnx_ok = False; print("ONNX export skipped:", e)
    json.dump({"classes": classes, "feature_spec": feature_spec, "metrics": metrics}, open(str(prefix) + ".json", "w"), indent=1)
    print("exported", str(prefix) + ".pt", "(+ .onnx)" if onnx_ok else "", "and", str(prefix) + ".json")

if __name__ == "__main__":
    main()
