#!/usr/bin/env python3
"""Is the GPU real and how fast is the whale CNN on it? Runs one fwd/bwd of WhaleCNN at the pretrain batch size.

    python infra/gpu_check.py            # width 64, batch 256 (configs/pretrain_gpu.json)
    python infra/gpu_check.py --width 32 --batch 128
"""
import argparse, json, pathlib, sys, time
import torch
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "whale_cnn"))
from train import WhaleCNN, device  # noqa: E402

ap = argparse.ArgumentParser()
cfg = json.load(open(HERE.parent / "configs" / "pretrain_gpu.json"))
ap.add_argument("--width", type=int, default=cfg["width"]); ap.add_argument("--batch", type=int, default=cfg["batch"])
ap.add_argument("--steps", type=int, default=10); ap.add_argument("--classes", type=int, default=22)
a = ap.parse_args()
dev = device(); print("device", dev, torch.cuda.get_device_name(0) if dev.type == "cuda" else "")
model = WhaleCNN(a.classes, width=a.width).to(dev); opt = torch.optim.AdamW(model.parameters())
print(f"WhaleCNN width={a.width}: {sum(p.numel() for p in model.parameters())/1e6:.2f} M params")
x = torch.randn(a.batch, 1, 128, 301, device=dev); y = torch.randint(0, a.classes, (a.batch,), device=dev)
for i in range(a.steps + 2):
    if i == 2: (torch.cuda.synchronize() if dev.type == "cuda" else None); t0 = time.time()
    opt.zero_grad(); torch.nn.functional.cross_entropy(model(x), y).backward(); opt.step()
if dev.type == "cuda": torch.cuda.synchronize()
dt = (time.time() - t0) / a.steps
print(f"{dt*1000:.0f} ms / step at batch {a.batch}  ->  {cfg['steps_per_epoch']*dt:.0f} s / epoch at steps_per_epoch={cfg['steps_per_epoch']}")
if dev.type == "cuda": print(f"peak mem {torch.cuda.max_memory_allocated()/2**30:.1f} GB")
