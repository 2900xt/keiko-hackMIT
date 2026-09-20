#!/usr/bin/env python3
"""List our own hydrophone recordings (pipeline/out/<BUOY>-<YYYYMMDDTHHMMSS>.wav, UTC) as a labeling sheet.

    python data/charles_manifest.py                 # -> data/charles_clips.csv
    python data/charles_manifest.py --dirs ../../pipeline/out ../../site/data/clips

Columns: clip_id, file_path (relative to repo root when inside it), buoy, ts_utc, duration_s, sr, rms_db, label (EMPTY: fill in from
configs/charles_labels.csv by listening / from the site's detections.csv), group (recording session = UTC hour, so the
train/val/test split in charles_features.py never puts one session in two splits).
"""
import argparse, pathlib, re, sys
import numpy as np, pandas as pd, soundfile as sf

HERE = pathlib.Path(__file__).resolve().parent; ROOT = HERE.parents[2]
NAME = re.compile(r"(?P<buoy>[A-Z0-9]+-\d+)-(?P<ts>\d{8}T\d{6})\.wav$")

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dirs", nargs="+", type=pathlib.Path, default=[ROOT / "pipeline" / "out", ROOT / "site" / "data" / "clips"])
    ap.add_argument("--out", type=pathlib.Path, default=HERE / "charles_clips.csv")
    ap.add_argument("--detections", type=pathlib.Path, default=ROOT / "site" / "data" / "detections.csv", help="prefill label=species for field detections")
    a = ap.parse_args()
    prev = pd.read_csv(a.out) if a.out.exists() else None   # keep labels already typed in
    det = pd.read_csv(a.detections) if a.detections.exists() else None
    rows = []
    for d in a.dirs:
        for p in sorted(d.glob("*.wav")):
            m = NAME.search(p.name)
            if not m: continue
            info = sf.info(p); y, sr = sf.read(p, dtype="float32", always_2d=True); y = y.mean(1)
            ts = pd.to_datetime(m["ts"], format="%Y%m%dT%H%M%S", utc=True)
            rows.append(dict(clip_id=p.stem, file_path=str(p.relative_to(ROOT) if p.resolve().is_relative_to(ROOT) else p.resolve()), buoy=m["buoy"], ts_utc=ts.isoformat(),
                             duration_s=round(info.duration, 2), sr=sr, rms_db=round(20 * np.log10(np.sqrt(np.mean(y ** 2)) + 1e-9), 1),
                             label="", group=ts.strftime("%Y%m%dT%H")))
    df = pd.DataFrame(rows).drop_duplicates("clip_id")
    if df.empty: sys.exit("no <BUOY>-<timestamp>.wav files found in " + ", ".join(map(str, a.dirs)))
    if det is not None:
        field = det[det.source == "field"].set_index("id").species.replace("unknown", "")
        df["label"] = df.clip_id.map(field).fillna("")
    if prev is not None:
        df["label"] = df.clip_id.map(prev.set_index("clip_id").label).fillna(df.label)
    df.to_csv(a.out, index=False)
    print(f"{len(df)} clips, {df.duration_s.sum()/60:.1f} min, {(df.label != '').sum()} labeled -> {a.out}")
    print(df.groupby("group").size().rename("clips per session").to_string())

if __name__ == "__main__": main()
