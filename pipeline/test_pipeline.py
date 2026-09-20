#!/usr/bin/env python3
"""Offline regression for keiko_pipeline.py (run with the pipeline venv: `make test`).

  1. 20 s of white noise at the UNO Q's 3333 Hz  -> must produce no events
  2. samples/humpback_nps.mp3 (real humpback song) -> must produce a humpback event
"""
import os, pathlib, subprocess, sys, tempfile
import numpy as np, soundfile as sf

HERE = pathlib.Path(__file__).resolve().parent
PY = sys.executable

def run(wav, out):
    r = subprocess.run([PY, str(HERE / "keiko_pipeline.py"), "--wav", str(wav), "--out", str(out), "--quiet"],
                       capture_output=True, text=True)
    if r.returncode:
        print(r.stdout, r.stderr); sys.exit(f"pipeline failed on {wav}")
    return [l for l in r.stdout.splitlines() if l.startswith("EVENT")]

tmp = pathlib.Path(tempfile.mkdtemp())
noise = tmp / "noise.wav"
sf.write(noise, np.random.default_rng(0).normal(0, 0.05, 20 * 3333).astype("float32"), 3333, subtype="PCM_16")
ev = run(noise, tmp / "out_noise")
assert not ev, f"white noise produced events: {ev}"
print("noise: 0 events  ok")

ev = run(HERE / "samples" / "humpback_nps.mp3", tmp / "out_humpback")
assert ev and any("humpback" in l for l in ev), f"humpback sample: {ev or 'no events'}"
print(f"humpback: {len(ev)} event(s), first: {ev[0][:80]}  ok")
