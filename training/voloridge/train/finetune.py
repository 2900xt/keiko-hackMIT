#!/usr/bin/env python3
"""Transfer the pretrained whale CNN to our own recordings: new head for the Charles label set, early blocks frozen.

    python train/finetune.py --config configs/finetune_charles.json
    python train/finetune.py --config configs/finetune_charles.json --freeze_blocks 0 --lr 1e-4   # overrides
    python train/finetune.py --eval runs/charles_ft/best.pt --features data/charles_v2

Loads a checkpoint written by ../whale_cnn/train.py (runs/*/best.pt or models/*.pt), keeps stem + features, replaces
the linear head with one sized to the Charles classes, freezes stem + the first `freeze_blocks` ConvBlocks (their
BatchNorm stays in eval mode so the pretrained statistics survive small batches), and trains with a lower LR on the
unfrozen trunk and `head_lr_mult` x that on the head. Class-balanced sampling, the same SpecAugment as pretraining
(bandwidth masking off: our recorder is fixed), best-val macro-F1 checkpoint, test metrics via whale_cnn.evaluate.
Export format matches whale_cnn's, so pipeline/keiko_pipeline.py --model can load the result.
"""
import argparse, json, pathlib, sys, time
import numpy as np, pandas as pd, torch, torch.nn as nn, torch.nn.functional as F
from torch.utils.data import DataLoader, WeightedRandomSampler

HERE = pathlib.Path(__file__).resolve().parent; VOLO = HERE.parent
sys.path.insert(0, str(VOLO.parent / "whale_cnn"))
import train as wc  # noqa: E402  (WhaleCNN, WindowDataset, evaluate, device, export_model)

def load_pretrained(path, dev):
    ck = torch.load(path, map_location=dev)
    width = ck.get("arch", {}).get("width") or ck.get("config", {}).get("width", 32)
    model = wc.WhaleCNN(len(ck["classes"]), width=width); model.load_state_dict(ck["model"])
    return model, width, ck["classes"]

def freeze(model, n_blocks):
    frozen = [model.stem] + list(model.features[:n_blocks])
    for mod in frozen:
        for p in mod.parameters(): p.requires_grad = False
    return frozen

def set_frozen_bn_eval(frozen):
    for mod in frozen:
        for m in mod.modules():
            if isinstance(m, nn.BatchNorm2d): m.eval()

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=pathlib.Path, help="json with any of the args below; CLI overrides")
    ap.add_argument("--init", type=pathlib.Path); ap.add_argument("--features", type=pathlib.Path)
    ap.add_argument("--name", default="charles_ft"); ap.add_argument("--freeze_blocks", type=int, default=2)
    ap.add_argument("--epochs", type=int, default=30); ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--lr", type=float, default=5e-4); ap.add_argument("--head_lr_mult", type=float, default=10.0)
    ap.add_argument("--steps_per_epoch", type=int, default=100); ap.add_argument("--patience", type=int, default=6)
    ap.add_argument("--dropout", type=float, default=0.5); ap.add_argument("--label_smoothing", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=0); ap.add_argument("--export", default="models/whale_cnn_charles")
    ap.add_argument("--eval", type=pathlib.Path, help="evaluate this fine-tuned checkpoint on test instead of training")
    a = ap.parse_args()
    if a.config:
        cfg = {k: v for k, v in json.load(open(a.config)).items() if not k.startswith("_")}
        cli = {k for k in vars(a) if f"--{k}" in sys.argv}
        for k, v in cfg.items():
            if k not in cli: setattr(a, k, pathlib.Path(v) if k in ("init", "features") else v)
    for k in ("init", "features"):
        if getattr(a, k) is None: sys.exit(f"--{k} required (or in --config)")
        if not getattr(a, k).is_absolute(): setattr(a, k, (VOLO / getattr(a, k)).resolve())
    torch.manual_seed(a.seed); np.random.seed(a.seed); dev = wc.device(); print("device", dev)

    X, m, classes = wc.load_data(a.features, merge_rare=False, in_ram=True)
    print(f"{len(m)} windows, {len(classes)} classes: {classes}")
    out = VOLO / "runs" / a.name; out.mkdir(parents=True, exist_ok=True)

    if a.eval:
        ck = torch.load(a.eval, map_location=dev); model = wc.WhaleCNN(len(ck["classes"]), width=ck["arch"]["width"]).to(dev)
        model.load_state_dict(ck["model"]); macro, acc, cmacro, _ = wc.evaluate(model, X, m, "test", classes, dev, a.batch, out, "test")
        print(f"TEST window macro-F1 {macro:.3f}  acc {acc:.3f}  clip-level macro-F1 {cmacro:.3f}"); return

    model, width, pre_classes = load_pretrained(a.init, dev)
    print(f"init {a.init.name}: width {width}, {len(pre_classes)} pretrained classes")
    model.head = nn.Sequential(nn.Dropout(a.dropout), nn.Linear(width * 8 * 2, len(classes)))
    frozen = freeze(model, a.freeze_blocks); model.to(dev)
    n_train = sum(p.numel() for p in model.parameters() if p.requires_grad); n_all = sum(p.numel() for p in model.parameters())
    print(f"trainable {n_train/1e6:.2f} M of {n_all/1e6:.2f} M (stem + {a.freeze_blocks} blocks frozen)")

    tr = m.index[m.split == "train"].values; va = m.index[m.split == "val"].values
    counts = np.bincount(m.y.values[tr], minlength=len(classes)); w = 1 / np.sqrt(np.maximum(counts, 1))
    sampler = WeightedRandomSampler(torch.as_tensor(w[m.y.values[tr]], dtype=torch.double), a.steps_per_epoch * a.batch, replacement=True)
    dl_tr = DataLoader(wc.WindowDataset(X, tr, m.y.values[tr], augment=True, lowpass=False), batch_size=a.batch, sampler=sampler, num_workers=0)
    trunk = [p for n, p in model.named_parameters() if p.requires_grad and not n.startswith("head")]
    opt = torch.optim.AdamW([{"params": trunk, "lr": a.lr}, {"params": model.head.parameters(), "lr": a.lr * a.head_lr_mult}], weight_decay=1e-2)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=[a.lr, a.lr * a.head_lr_mult], total_steps=a.epochs * a.steps_per_epoch)

    best, bad = -1, 0
    for ep in range(a.epochs):
        model.train(); set_frozen_bn_eval(frozen); t0 = time.time(); tot = 0.0
        for x, y in dl_tr:
            x, y = x.to(dev), y.to(dev); opt.zero_grad()
            loss = F.cross_entropy(model(x), y, label_smoothing=a.label_smoothing); loss.backward(); opt.step(); sched.step(); tot += loss.item()
        vmacro, vacc, _, _ = wc.evaluate(model, X, m, "val", classes, dev, a.batch)
        print(f"ep {ep:02d} loss {tot/len(dl_tr):.3f}  val macro-F1 {vmacro:.3f} acc {vacc:.3f}  {time.time()-t0:.0f}s")
        if vmacro > best:
            best, bad = vmacro, 0
            torch.save({"model": model.state_dict(), "classes": classes, "arch": {"width": width, "n_classes": len(classes)},
                        "config": {k: str(v) for k, v in vars(a).items()}, "init": str(a.init)}, out / "best.pt")
        else:
            bad += 1
            if bad >= a.patience: print("early stop"); break

    model.load_state_dict(torch.load(out / "best.pt", map_location=dev)["model"])
    macro, acc, cmacro, rep = wc.evaluate(model, X, m, "test", classes, dev, a.batch, out, "test")
    print(f"TEST window macro-F1 {macro:.3f}  acc {acc:.3f}  clip-level macro-F1 {cmacro:.3f}")
    for c in classes:
        if c in rep: print(f"  {c:20s} f1={rep[c]['f1-score']:.2f} n={int(rep[c]['support'])}")
    if a.export:
        a.width = width  # export_model reads a.width
        wc.export_model(model, classes, a, out, VOLO / a.export, {"test_window_macro_f1": macro, "test_acc": acc, "test_clip_macro_f1": cmacro, "init": str(a.init)})

if __name__ == "__main__": main()
