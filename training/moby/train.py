#!/usr/bin/env python3
"""Moby: two-branch ensemble right-whale detector (ISEF poster, Figure 8), PyTorch.

    python3 train.py                        # 5-fold ensemble on ../dataset/features/moby_narw.npz, ~15 min on an M-series GPU
    python3 train.py --folds 1 --epochs 5   # one quick model
    python3 train.py --eval models/moby_narw.pt

Architecture (per fold model, ~350k parameters):
    2D branch  (1, 103, 126) -> Conv2d 1>16>32>64>128 (3x3 + BN + ReLU + MaxPool 2x2) -> CBAM (channel + spatial attention)
               -> global mean & max pool -> 256
    1D branch  (7, 126) -> Conv1d 7>64>128 (k5 + BN + ReLU + MaxPool 2) -> BiLSTM(64) -> mean over time -> 128
    head       concat 384 -> Dense 256 -> ReLU -> Dropout -> Dense 64 -> ReLU -> Dense 2 (softmax)
Per-row feature z-scoring lives inside the model (buffers), so raw features from features.clip_features() go straight in.

Data: 15% of clips held out as the test set; the remaining 85% is split into K stratified folds. Fold k's model
trains on the other folds and early-stops on fold k's AUROC. The *ensemble* is the mean softmax of the K models,
reported on the held-out test set next to the single-model mean +/- std.
Augmentation (train only, on the GPU batch): Gaussian blur on the 2D stack, time dilation 0.85-1.15x applied to both
branches together, random gain, one time mask.
"""
import argparse, json, pathlib, time
import numpy as np, torch, torch.nn as nn, torch.nn.functional as F
from sklearn.metrics import roc_auc_score, accuracy_score, f1_score
from sklearn.model_selection import StratifiedKFold, train_test_split

HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_FEATURES = HERE.parent / "dataset" / "features" / "moby_narw.npz"


# ----------------------------------------------------------------------------- model
class CBAM(nn.Module):
    """Convolutional Block Attention Module: channel attention (shared MLP over avg- and max-pooled maps), then
    spatial attention (7x7 conv over the channel-mean and channel-max maps)."""
    def __init__(self, c, r=16):
        super().__init__()
        self.mlp = nn.Sequential(nn.Linear(c, c // r), nn.ReLU(inplace=True), nn.Linear(c // r, c))
        self.spatial = nn.Conv2d(2, 1, 7, padding=3)
    def forward(self, x):
        ca = torch.sigmoid(self.mlp(x.mean((2, 3))) + self.mlp(x.amax((2, 3))))[:, :, None, None]
        x = x * ca
        sa = torch.sigmoid(self.spatial(torch.cat([x.mean(1, keepdim=True), x.amax(1, keepdim=True)], 1)))
        return x * sa


def conv2d_block(cin, cout):
    return nn.Sequential(nn.Conv2d(cin, cout, 3, padding=1, bias=False), nn.BatchNorm2d(cout), nn.ReLU(inplace=True), nn.MaxPool2d(2))


def conv1d_block(cin, cout):
    return nn.Sequential(nn.Conv1d(cin, cout, 5, padding=2, bias=False), nn.BatchNorm1d(cout), nn.ReLU(inplace=True), nn.MaxPool1d(2))


class Moby(nn.Module):
    def __init__(self, rows2d=103, rows1d=7, lstm=64, dropout=0.3, mu2=None, sd2=None, mu1=None, sd1=None):
        super().__init__()
        self.register_buffer("mu2", torch.zeros(rows2d, 1) if mu2 is None else mu2)
        self.register_buffer("sd2", torch.ones(rows2d, 1) if sd2 is None else sd2)
        self.register_buffer("mu1", torch.zeros(rows1d, 1) if mu1 is None else mu1)
        self.register_buffer("sd1", torch.ones(rows1d, 1) if sd1 is None else sd1)
        self.branch2d = nn.Sequential(conv2d_block(1, 16), conv2d_block(16, 32), conv2d_block(32, 64), conv2d_block(64, 128), CBAM(128))
        self.branch1d = nn.Sequential(conv1d_block(rows1d, 64), conv1d_block(64, 128))
        self.lstm = nn.LSTM(128, lstm, batch_first=True, bidirectional=True)
        self.head = nn.Sequential(nn.Linear(256 + 2 * lstm, 256), nn.ReLU(inplace=True), nn.Dropout(dropout),
                                  nn.Linear(256, 64), nn.ReLU(inplace=True), nn.Linear(64, 2))

    def forward(self, x2, x1):                                   # x2 (B, 103, 126) raw, x1 (B, 7, 126) raw
        x2 = ((x2 - self.mu2) / self.sd2)[:, None]               # (B, 1, 103, 126)
        x1 = (x1 - self.mu1) / self.sd1
        h2 = self.branch2d(x2)                                   # (B, 128, 6, 7)
        h2 = torch.cat([h2.mean((2, 3)), h2.amax((2, 3))], 1)    # (B, 256)
        h1, _ = self.lstm(self.branch1d(x1).transpose(1, 2))     # (B, 31, 128)
        return self.head(torch.cat([h2, h1.mean(1)], 1))         # (B, 2) logits


class Ensemble(nn.Module):
    """Mean softmax over the fold models -> P(whale)."""
    def __init__(self, models):
        super().__init__(); self.models = nn.ModuleList(models)
    def forward(self, x2, x1):
        return torch.stack([F.softmax(m(x2, x1), 1)[:, 1] for m in self.models]).mean(0)


# ----------------------------------------------------------------------------- augmentation (batched, on device)
def gaussian_blur(x, sigma):
    k = torch.arange(-3, 4, device=x.device, dtype=x.dtype); g = torch.exp(-k ** 2 / (2 * sigma ** 2)); g = g / g.sum()
    x = F.conv2d(x[:, None], g.view(1, 1, 1, 7), padding=(0, 3))
    return F.conv2d(x, g.view(1, 1, 7, 1), padding=(3, 0))[:, 0]


def augment(x2, x1):
    B, _, T = x2.shape
    if np.random.rand() < 0.5:
        x2 = gaussian_blur(x2, float(np.random.uniform(0.5, 1.5)))
    r = float(np.random.uniform(0.85, 1.15))                     # time dilation, same factor for both branches
    Tn = max(8, int(T * r))
    x2 = F.interpolate(x2, size=Tn, mode="linear", align_corners=False)     # (B, rows, Tn)
    x1 = F.interpolate(x1, size=Tn, mode="linear", align_corners=False)
    if Tn >= T:
        s = np.random.randint(0, Tn - T + 1); x2, x1 = x2[..., s:s + T], x1[..., s:s + T]
    else:
        p = T - Tn; x2, x1 = F.pad(x2, (0, p), mode="replicate"), F.pad(x1, (0, p), mode="replicate")
    x2 = x2 + torch.randn(B, 1, 1, device=x2.device) * 0.5       # gain jitter (features are z-scored per row -> additive)
    t0, tw = np.random.randint(0, T - 20), np.random.randint(0, 20)
    x2 = x2.clone(); x2[..., t0:t0 + tw] = 0
    return x2, x1


# ----------------------------------------------------------------------------- training
def device():
    return torch.device("mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu")


def batches(X2, X1, y, idx, bs, shuffle):
    idx = np.random.permutation(idx) if shuffle else idx
    for s in range(0, len(idx), bs):
        b = np.sort(idx[s:s + bs])
        yield torch.from_numpy(X2[b].astype(np.float32)), torch.from_numpy(X1[b].astype(np.float32)), torch.from_numpy(y[b].astype(np.int64))


@torch.no_grad()
def probs(model, X2, X1, y, idx, dev, bs=512):
    model.eval(); out = []
    for x2, x1, _ in batches(X2, X1, y, idx, bs, False):
        p = model(x2.to(dev), x1.to(dev))
        out.append((F.softmax(p, 1)[:, 1] if p.ndim == 2 else p).cpu())
    return torch.cat(out).numpy()


def metrics(y, p):
    return {"auroc": float(roc_auc_score(y, p)), "acc": float(accuracy_score(y, p > 0.5)), "f1": float(f1_score(y, p > 0.5))}


def stats(X, idx):
    """Per-row mean / std over the training clips (row = feature row, pooled over clips and time)."""
    x = X[idx].astype(np.float32); return torch.from_numpy(x.mean((0, 2))[:, None]), torch.from_numpy(x.std((0, 2))[:, None] + 1e-6)


def train_fold(X2, X1, y, tr, va, a, dev, fold):
    mu2, sd2 = stats(X2, tr); mu1, sd1 = stats(X1, tr)
    model = Moby(X2.shape[1], X1.shape[1], a.lstm, a.dropout, mu2, sd2, mu1, sd1).to(dev)
    steps = a.epochs * int(np.ceil(len(tr) / a.batch))
    opt = torch.optim.AdamW(model.parameters(), a.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, a.lr, total_steps=steps, pct_start=0.2)
    pos = y[tr].mean(); w = torch.tensor([1.0, float((1 - pos) / pos) ** 0.5], device=dev)     # soft class weight (~1.8 on whale)
    best, best_state, bad = -1, None, 0
    for ep in range(a.epochs):
        model.train(); t0, tot = time.time(), 0.0
        for x2, x1, yb in batches(X2, X1, y, tr, a.batch, True):
            x2, x1, yb = x2.to(dev), x1.to(dev), yb.to(dev)
            with torch.no_grad():
                x2n, x1n = augment((x2 - model.mu2) / model.sd2, (x1 - model.mu1) / model.sd1)
                x2, x1 = x2n * model.sd2 + model.mu2, x1n * model.sd1 + model.mu1          # augment in z-space, feed raw
            loss = F.cross_entropy(model(x2, x1), yb, weight=w, label_smoothing=0.05)
            opt.zero_grad(set_to_none=True); loss.backward(); nn.utils.clip_grad_norm_(model.parameters(), 5.0); opt.step(); sched.step()
            tot += loss.item() * len(yb)
        m = metrics(y[va], probs(model, X2, X1, y, va, dev))
        print(f"  fold {fold} ep {ep + 1:2d}/{a.epochs}  loss {tot / len(tr):.4f}  val auroc {m['auroc']:.4f} acc {m['acc']:.3f} f1 {m['f1']:.3f}  {time.time() - t0:.0f}s")
        if m["auroc"] > best:
            best, bad, best_state = m["auroc"], 0, {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        else:
            bad += 1
            if bad >= a.patience: print("  early stop"); break
    model.load_state_dict(best_state)
    return model, best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", type=pathlib.Path, default=DEFAULT_FEATURES)
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--patience", type=int, default=5)
    ap.add_argument("--batch", type=int, default=128)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--lstm", type=int, default=64)
    ap.add_argument("--dropout", type=float, default=0.3)
    ap.add_argument("--test_frac", type=float, default=0.15)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=pathlib.Path, default=HERE / "models" / "moby_narw.pt")
    ap.add_argument("--eval", type=pathlib.Path, help="evaluate a saved ensemble on the same held-out test split")
    a = ap.parse_args()
    np.random.seed(a.seed); torch.manual_seed(a.seed); dev = device()
    d = np.load(a.features); X2, X1, y = d["X2"], d["X1"], d["y"].astype(np.int64)
    print(f"{len(y)} clips  X2 {X2.shape[1:]}  X1 {X1.shape[1:]}  whale {y.mean():.1%}  device {dev}")
    dev_idx, te = train_test_split(np.arange(len(y)), test_size=a.test_frac, stratify=y, random_state=a.seed)

    if a.eval:
        ens = load_ensemble(a.eval).to(dev)
        print("test (ensemble):", metrics(y[te], probs(ens, X2, X1, y, te, dev))); return

    models, fold_val, fold_test = [], [], []
    if a.folds > 1:
        splits = StratifiedKFold(a.folds, shuffle=True, random_state=a.seed).split(dev_idx, y[dev_idx])
        splits = [(dev_idx[tr], dev_idx[va]) for tr, va in splits]
    else:
        tr, va = train_test_split(dev_idx, test_size=0.15 / (1 - a.test_frac), stratify=y[dev_idx], random_state=a.seed); splits = [(tr, va)]
    print(f"train ~{len(splits[0][0])}  val ~{len(splits[0][1])}  test {len(te)}  ({len(splits)} fold(s))")
    n_params = sum(p.numel() for p in Moby(X2.shape[1], X1.shape[1], a.lstm).parameters()); print(f"parameters per model: {n_params:,}")
    for k, (tr, va) in enumerate(splits):
        model, best = train_fold(X2, X1, y, tr, va, a, dev, k)
        mt = metrics(y[te], probs(model, X2, X1, y, te, dev))
        print(f"fold {k}: best val auroc {best:.4f}   test auroc {mt['auroc']:.4f} acc {mt['acc']:.3f} f1 {mt['f1']:.3f}")
        models.append(model); fold_val.append(best); fold_test.append(mt)
    ens = Ensemble(models).to(dev)
    me = metrics(y[te], probs(ens, X2, X1, y, te, dev))
    ta = np.array([m["auroc"] for m in fold_test])
    print(f"\nsingle model test AUROC {ta.mean():.4f} +/- {ta.std():.4f}   ENSEMBLE test AUROC {me['auroc']:.4f} acc {me['acc']:.3f} f1 {me['f1']:.3f}")

    a.out.parent.mkdir(parents=True, exist_ok=True)
    report = {"n_params_per_model": n_params, "folds": len(models), "fold_val_auroc": fold_val, "fold_test": fold_test, "ensemble_test": me,
              "test_indices": te.tolist(), "config": {k: (str(v) if isinstance(v, pathlib.Path) else v) for k, v in vars(a).items()}}
    torch.save({"models": [m.cpu().state_dict() for m in models], "arch": {"rows2d": X2.shape[1], "rows1d": X1.shape[1], "lstm": a.lstm},
                "features": {"sr": 2000, "clip_s": 2.0, "n_fft": 512, "hop": 32, "rows2d": "logmel64|mfcc20|chroma12|contrast7",
                             "rows1d": "log_rms,centroid,bandwidth,rolloff,flatness,zcr,f0_yin"}, "report": report}, a.out)
    json.dump(report, open(a.out.with_suffix(".json"), "w"), indent=1)
    print(f"saved {a.out} (+ .json report)")
    try:
        ens.cpu().eval()
        torch.onnx.export(ens, (torch.zeros(1, X2.shape[1], X2.shape[2]), torch.zeros(1, X1.shape[1], X1.shape[2])), str(a.out.with_suffix(".onnx")),
                          input_names=["x2d", "x1d"], output_names=["p_whale"], dynamic_axes={"x2d": {0: "b"}, "x1d": {0: "b"}, "p_whale": {0: "b"}},
                          opset_version=17, dynamo=False)
        print(f"saved {a.out.with_suffix('.onnx')}")
    except Exception as e:
        print(f"onnx export skipped: {e}")


def load_ensemble(path):
    ck = torch.load(path, map_location="cpu", weights_only=False)
    ms = []
    for sd in ck["models"]:
        m = Moby(ck["arch"]["rows2d"], ck["arch"]["rows1d"], ck["arch"]["lstm"]); m.load_state_dict(sd); ms.append(m)
    return Ensemble(ms).eval()


if __name__ == "__main__":
    main()
