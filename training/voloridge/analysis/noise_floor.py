#!/usr/bin/env python3
"""Hourly underwater noise floor from our own recordings (pipeline/out/<BUOY>-<YYYYMMDDTHHMMSS>.wav, UTC).

    python analysis/noise_floor.py                     # -> analysis/out/noise_floor_hourly.csv (+ per-clip csv)
    python analysis/noise_floor.py --dirs ../../pipeline/out /path/to/more/wavs

Per clip: 1 s Hann frames, power spectrum, band levels in dB re full scale for 10-100 / 100-1000 / 1-4 kHz, and the
*floor* = 30th percentile of the 10-1000 Hz band level over the clip's frames — the same statistic the live pipeline
tracks as `floor` (keiko_pipeline.py), i.e. what is left when boats and calls are excluded. Then median per UTC hour.
Levels are relative (the analog front end is uncalibrated), so only differences between hours mean anything — which
is all the weather join needs.
"""
import argparse, pathlib, re, sys
import numpy as np, pandas as pd, soundfile as sf

HERE = pathlib.Path(__file__).resolve().parent; ROOT = HERE.parents[2]
NAME = re.compile(r"(?P<buoy>[A-Z0-9]+-\d+)-(?P<ts>\d{8}T\d{6})\.wav$")
BANDS = {"lf_10_100": (10, 100), "mf_100_1k": (100, 1000), "hf_1k_4k": (1000, 4000)}

def band_levels(y, sr, frame_s=1.0):
    n = int(frame_s * sr); win = np.hanning(n); freqs = np.fft.rfftfreq(n, 1 / sr)
    frames = [y[i:i + n] * win for i in range(0, len(y) - n + 1, n)] or [np.pad(y, (0, n - len(y))) * win]
    P = np.abs(np.fft.rfft(np.stack(frames), axis=1)) ** 2 / n
    out = {}
    for name, (lo, hi) in BANDS.items():
        sel = (freqs >= lo) & (freqs < min(hi, sr / 2))
        out[name] = 10 * np.log10(P[:, sel].sum(1) + 1e-12) if sel.any() else np.full(len(P), np.nan)
    return out

def clip_stats(p):
    m = NAME.search(p.name)
    if not m: return None
    y, sr = sf.read(p, dtype="float32", always_2d=True); y = y.mean(1); y -= y.mean()
    lv = band_levels(y, sr); wide = 10 * np.log10(10 ** (lv["lf_10_100"] / 10) + 10 ** (lv["mf_100_1k"] / 10))
    return dict(clip_id=p.stem, buoy=m["buoy"], ts_utc=pd.to_datetime(m["ts"], format="%Y%m%dT%H%M%S", utc=True),
                duration_s=round(len(y) / sr, 2), sr=sr, rms_db=20 * np.log10(np.sqrt(np.mean(y ** 2)) + 1e-9),
                floor_db=float(np.percentile(wide, 30)), p90_db=float(np.percentile(wide, 90)),
                **{f"{k}_db": float(np.median(v)) for k, v in lv.items()})

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dirs", nargs="+", type=pathlib.Path, default=[ROOT / "pipeline" / "out"])
    ap.add_argument("--out", type=pathlib.Path, default=HERE / "out" / "noise_floor_hourly.csv")
    a = ap.parse_args()
    rows = [r for d in a.dirs for r in map(clip_stats, sorted(d.glob("*.wav"))) if r]
    if not rows: sys.exit("no <BUOY>-<timestamp>.wav files in " + ", ".join(map(str, a.dirs)))
    clips = pd.DataFrame(rows); a.out.parent.mkdir(parents=True, exist_ok=True)
    clips.to_csv(a.out.with_name("noise_floor_clips.csv"), index=False)
    clips["ts"] = clips.ts_utc.dt.floor("h")
    cols = ["floor_db", "p90_db", "rms_db"] + [f"{k}_db" for k in BANDS]
    h = clips.groupby(["buoy", "ts"]).agg(**{c: (c, "median") for c in cols}, n_clips=("clip_id", "size"), seconds=("duration_s", "sum")).reset_index()
    h.to_csv(a.out, index=False)
    print(f"{len(clips)} clips ({clips.duration_s.sum()/60:.1f} min) -> {len(h)} buoy-hours, {h.ts.min()} .. {h.ts.max()} -> {a.out}")
    print(h[["ts", "floor_db", "p90_db", "n_clips"]].to_string(index=False))

if __name__ == "__main__": main()
