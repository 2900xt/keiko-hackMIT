#!/usr/bin/env python3
"""Reshape every kept whale source into the Kaggle whale-detection-challenge layout.

The Kaggle "Whale Detection Challenge" (Cornell / Marinexplore 2013) ships a flat folder of
fixed-length, mono, 16-bit clips plus a train.csv of `clip_name,label` (1 = right-whale
upcall, 0 = noise). This script produces the same thing for the whole cleaned corpus:

  <out>/train/<clip_name>.wav     fixed WIN seconds, mono, 16-bit PCM, SR Hz
  <out>/train.csv                 clip_name,label first (Kaggle header), then the metadata
                                  columns a location / species model needs

Sources:
  kaggle    the Kaggle zip itself (30,000 clips, 7,027 right-whale upcalls + 22,973 noise)
  watkins   Watkins cetacean cuts that passed the location-table cleaning (species, date,
            position); long cuts yield up to --max-watkins windows each
  dclde     DCLDE 2027 killer whale / humpback call boxes with per-call UTC from
            Annotations.csv; abiotic boxes become label 0; uncertain KW and "undetermined
            biological" boxes are dropped. DFO sites keep their audio but have no position.
  aad       Antarctic blue & fin whale calls with per-call UTC from the Raven tables;
            unidentified-call tables are dropped

Clips shorter than WIN are centre-padded with zeros and `pad_s` records how much. Longer
clips are cut into evenly spaced WIN windows. Every clip is peak-normalised to 0.9 full scale
(`gain_db` records the gain, so relative loudness can be undone). Default SR is 8 kHz, the Keiko buoy's
hydrophone rate; pass --sr 2000 to match the Kaggle clips exactly.

Usage:
  python3 build_whale_clips.py --db ~/Projects/marine-sounds-db --out ~/Projects/marine-sounds-db/whale-clips
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import math
import os
import re
import sqlite3
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd
import soundfile as sf
from scipy.signal import resample_poly

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "location"))
import build_whale_locations as loc  # noqa: E402

KAGGLE_SITE = ("kaggle:MassBay_MARU", "Massachusetts Bay (Cornell MARU array)", "Eubalaena glacialis", "North Atlantic right whale")

DCLDE_LABELS = {  # taxon_label in marine_sounds.sqlite -> (label, species, common, group, ecotype)
    "Humpback whale": (1, "Megaptera novaeangliae", "Humpback whale", "baleen whale", ""),
    "Southern Resident killer whale (SRKW)": (1, "Orcinus orca", "Killer whale", "toothed whale", "SRKW"),
    "Northern Resident killer whale (NRKW)": (1, "Orcinus orca", "Killer whale", "toothed whale", "NRKW"),
    "Bigg's / transient killer whale (TKW)": (1, "Orcinus orca", "Killer whale", "toothed whale", "TKW"),
    "Southern Alaska Resident killer whale (SAR)": (1, "Orcinus orca", "Killer whale", "toothed whale", "SAR"),
    "Offshore killer whale (OKW)": (1, "Orcinus orca", "Killer whale", "toothed whale", "OKW"),
    "Killer whale (ecotype unknown)": (1, "Orcinus orca", "Killer whale", "toothed whale", ""),
    "abiotic (non-biological)": (0, "", "noise", "", ""),
}

COLS = ["clip_name", "label", "species", "common_name", "taxon_group", "ecotype", "call_type", "datetime_utc", "time_precision",
        "lat", "lon", "coord_precision_km", "site_id", "location_name", "source", "source_clip", "orig_sr", "pad_s", "gain_db", "split"]

stats: list[tuple[str, str, int]] = []


def note(src: str, what: str, n: int) -> None:
    stats.append((src, what, int(n)))
    print(f"  {src:8s} {what:<60s} {n:>8,d}", file=sys.stderr)


def split_of(group_key: str, test_frac: float = 0.15) -> str:
    h = int(hashlib.md5(group_key.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return "test" if h < test_frac else "train"


# ----------------------------------------------------------------------------- source tables


def kaggle_table(db_root: Path) -> pd.DataFrame:
    k = db_root / "raw/kaggle_whale/data"
    t = pd.read_csv(k / "train.csv")
    note("kaggle", "labelled clips in train.csv", len(t))
    t = t[t.clip_name.map(lambda n: (k / "train" / n).exists())]
    note("kaggle", "clips present on disk", len(t))
    site, name, sp, common = KAGGLE_SITE
    return pd.DataFrame({
        "src": t.clip_name.map(lambda n: str(k / "train" / n)), "label": t.label.astype(int),
        "species": np.where(t.label == 1, sp, ""), "common_name": np.where(t.label == 1, common, "noise"),
        "taxon_group": np.where(t.label == 1, "baleen whale", ""), "ecotype": "", "call_type": np.where(t.label == 1, "upcall", ""),
        "datetime_utc": "", "time_precision": "none", "lat": np.nan, "lon": np.nan, "coord_precision_km": np.nan,
        "site_id": site, "location_name": name, "source": "kaggle", "source_clip": t.clip_name,
        "group": t.clip_name, "max_windows": 1, "stem": "kaggle_" + t.clip_name.str.replace(".aiff", "", regex=False),
    })


def watkins_table(db_root: Path) -> pd.DataFrame:
    df = loc.watkins_clips(db_root)
    return pd.DataFrame({
        "src": df.file_path.map(lambda p: str(db_root / p)), "label": 1, "species": df.scientific_name, "common_name": df.common_name,
        "taxon_group": df.taxon_group, "ecotype": "", "call_type": df.sound_type.fillna(""),
        "datetime_utc": df.date.dt.strftime("%Y-%m-%dT00:00:00Z"), "time_precision": "day",
        "lat": df.lat_out.round(4), "lon": df.lon_out.round(4), "coord_precision_km": df.coord_precision_km,
        "site_id": "watkins:" + df.lat_out.round(3).astype(str) + "," + df.lon_out.round(3).astype(str),
        "location_name": df.location.fillna("").str.strip().str.rstrip("OX ;"), "source": "watkins", "source_clip": df.source_record_id,
        "group": df.source_record_id.astype(str).str[:5], "max_windows": 0,  # filled from --max-watkins
        "stem": "watkins_" + df.source_record_id.astype(str),
    })


def dclde_table(db_root: Path, win: float, neg_per_file: int) -> pd.DataFrame:
    """Boxes become `cut` rows (centre time in the original recording); each fully annotated
    recording also contributes up to `neg_per_file` windows that overlap no annotation."""
    con = sqlite3.connect(db_root / "marine_sounds.sqlite")
    c = pd.read_sql("SELECT c.clip_id, c.taxon_label, c.location, c.source_record_id, c.note FROM clips c JOIN datasets d USING(dataset_id) WHERE d.name LIKE 'DCLDE%' AND d.downloaded=1", con)
    con.close()
    note("dclde", "call boxes in catalogue", len(c))
    m = c.taxon_label.isin(DCLDE_LABELS)
    note("dclde", "dropped: undetermined biological", (~m).sum())
    c = c[m]
    m = c.note.fillna("").str.contains("KW_certain=0")
    note("dclde", "dropped: annotator flagged killer whale as uncertain", m.sum())
    c = c[~m]

    originals = {os.path.basename(f): f for f in glob.glob(str(db_root / "raw/dclde2027_kw/*/audio/**/*.*"), recursive=True)}
    a = pd.read_csv(db_root / "raw/dclde2027_kw/Annotations.csv", usecols=["Soundfile", "Dataset", "FileBeginSec", "FileEndSec", "UTC", "FileOk"], low_memory=False)
    a["ts"] = pd.to_datetime(a.UTC, errors="coerce", utc=True, format="mixed")
    a["k"] = a.Soundfile + "@" + a.FileBeginSec.round(2).astype(str)
    utc = dict(zip(a.k, a.ts))
    sfile = c.source_record_id.str.split("@").str[0]
    span = c.source_record_id.str.split("@").str[1].str.split("-", expand=True).astype(float)
    begin, end = span[0], span[1]
    ts = (sfile + "@" + begin.round(2).astype(str)).map(utc)
    note("dclde", "per-call UTC matched from Annotations.csv", ts.notna().sum())
    m = sfile.isin(originals)
    note("dclde", "boxes whose original recording is on disk", m.sum())
    c, sfile, begin, end, ts = c[m], sfile[m], begin[m], end[m], ts[m]

    code = c.location.str.extract(r"/\s*([^\s(]+)")[0]
    site = code.map(loc._dclde_site)
    note("dclde", "boxes at sites with a published position", site.notna().sum())
    lab = c.taxon_label.map(DCLDE_LABELS)
    boxes = pd.DataFrame({
        "src": sfile.map(originals), "center_s": ((begin + end) / 2).round(3), "kind": "cut",
        "label": lab.str[0], "species": lab.str[1], "common_name": lab.str[2],
        "taxon_group": lab.str[3], "ecotype": lab.str[4], "call_type": np.where(lab.str[0] == 1, "call box", "abiotic box"),
        "datetime_utc": ts.dt.strftime("%Y-%m-%dT%H:%M:%SZ").fillna(""), "time_precision": np.where(ts.notna(), "second", "none"),
        "lat": site.map(lambda t: t[2] if t else np.nan), "lon": site.map(lambda t: t[3] if t else np.nan),
        "coord_precision_km": site.map(lambda t: t[4] if t else np.nan),
        "site_id": "dclde:" + code.fillna("unknown"), "location_name": site.map(lambda t: t[1] if t else "").where(site.notna(), c.location.fillna("")),
        "source": "dclde", "source_clip": c.source_record_id, "group": sfile, "max_windows": 1, "stem": "dclde_" + c.clip_id.astype(str),
    })

    # Negatives: windows that overlap no annotation of any class, from fully annotated files.
    ok = a[a.FileOk.astype(str).str.upper().eq("TRUE") & a.Soundfile.isin(originals)]
    file_start = (ok.ts - pd.to_timedelta(ok.FileBeginSec, unit="s")).groupby(ok.Soundfile).min()
    file_site = ok.groupby("Soundfile").Dataset.first()
    negs = []
    rng = np.random.default_rng(0)
    for sfn, g in ok.groupby("Soundfile"):
        ivals = sorted(zip(g.FileBeginSec, g.FileEndSec))
        # gaps between annotations with `win` clearance each side; the file end is unknown here so stop at the last annotation
        gaps, prev = [], 0.0
        for b, e in ivals:
            if b - prev >= 3 * win:
                gaps.append((prev + win, b - win))
            prev = max(prev, e)
        if not gaps:
            continue
        for _ in range(neg_per_file):
            g0, g1 = gaps[rng.integers(len(gaps))]
            negs.append((sfn, float(rng.uniform(g0, g1 - win)) + win / 2))
    n = pd.DataFrame(negs, columns=["Soundfile", "center_s"])
    n_site = n.Soundfile.map(file_site).map(loc._dclde_site)
    n_ts = n.Soundfile.map(file_start) + pd.to_timedelta(n.center_s, unit="s")
    negatives = pd.DataFrame({
        "src": n.Soundfile.map(originals), "center_s": n.center_s.round(3), "kind": "cut", "label": 0, "species": "", "common_name": "noise",
        "taxon_group": "", "ecotype": "", "call_type": "no-annotation window", "datetime_utc": n_ts.dt.strftime("%Y-%m-%dT%H:%M:%SZ").fillna(""),
        "time_precision": np.where(n_ts.notna(), "second", "none"),
        "lat": n_site.map(lambda t: t[2] if t else np.nan), "lon": n_site.map(lambda t: t[3] if t else np.nan), "coord_precision_km": n_site.map(lambda t: t[4] if t else np.nan),
        "site_id": "dclde:" + n.Soundfile.map(file_site).fillna("unknown"), "location_name": n_site.map(lambda t: t[1] if t else "").fillna(""),
        "source": "dclde", "source_clip": n.Soundfile + "@neg" + n.center_s.round(1).astype(str), "group": n.Soundfile, "max_windows": 1,
        "stem": "dclde_neg" + n.index.astype(str),
    })
    note("dclde", f"negative windows sampled between annotations (<= {neg_per_file} per file)", len(negatives))
    return pd.concat([boxes, negatives], ignore_index=True)


def aad_table(db_root: Path) -> pd.DataFrame:
    con = sqlite3.connect(db_root / "marine_sounds.sqlite")
    c = pd.read_sql("SELECT c.clip_id, c.species_id, c.taxon_label, c.sound_type, c.observation_date, c.location, c.source_record_id, c.file_path FROM clips c JOIN datasets d USING(dataset_id) WHERE d.name LIKE 'AcousticTrends%'", con)
    con.close()
    note("aad", "call clips with audio on disk", len(c))
    m = c.species_id.isna()
    note("aad", "dropped: unidentified call (no species)", m.sum())
    c = c[~m]

    base = db_root / "raw/aad_bluefin"
    fs = pd.read_csv(base / "01-Documentation/folderStructure.csv")
    coords = {str(r.Folder).replace("\\", "").strip("/"): (float(r.Latitude), float(r.Longitude), str(r.SiteCode)) for _, r in fs.iterrows()}
    ts_map: dict[str, pd.Timestamp] = {}
    for folder in coords:
        for f in glob.glob(str(base / folder / "*.txt")):
            if "backbeat" in f.lower():
                continue
            t = pd.read_csv(f, sep="\t", low_memory=False, on_bad_lines="skip", encoding_errors="replace")
            t.columns = [x.strip().lower() for x in t.columns]
            col = next((x for x in t.columns if x.startswith("begin date time")), None)
            if col is None or "selection" not in t.columns:
                continue
            parsed = pd.to_datetime(t[col].astype(str).str.replace(r"\s+", " ", regex=True).str.strip(), errors="coerce", utc=True, format="mixed")
            for sel, ts in zip(t["selection"], parsed):
                ts_map[f"{folder}/{Path(f).name}#{sel}"] = ts
    ts = c.source_record_id.map(ts_map)
    note("aad", "per-call UTC matched from Raven tables", ts.notna().sum())
    fallback = pd.to_datetime(c.observation_date, errors="coerce", utc=True, format="mixed")
    ts = ts.fillna(fallback)
    prec = np.where(c.source_record_id.map(ts_map).notna(), "second", np.where(fallback.notna(), "day", "none"))
    folder = c.source_record_id.str.split("/").str[0]
    sp_common = c.taxon_label.map({
        "Antarctic blue whale": ("Balaenoptera musculus intermedia", "Antarctic blue whale"), "Fin whale": ("Balaenoptera physalus", "Fin whale"),
        "Antarctic minke whale": ("Balaenoptera bonaerensis", "Antarctic minke whale"), "Humpback whale": ("Megaptera novaeangliae", "Humpback whale"),
    })
    m = sp_common.isna()
    if m.any():
        note("aad", "dropped: unrecognised taxon label", m.sum())
    c, ts, prec, folder, sp_common = c[~m], ts[~m], prec[~m.values], folder[~m], sp_common[~m]
    return pd.DataFrame({
        "src": c.file_path.map(lambda p: str(db_root / p)), "label": 1, "species": sp_common.str[0], "common_name": sp_common.str[1],
        "taxon_group": "baleen whale", "ecotype": "", "call_type": c.sound_type.fillna("").str.split(" ").str[0],
        "datetime_utc": ts.dt.strftime("%Y-%m-%dT%H:%M:%SZ").fillna(""), "time_precision": prec,
        "lat": folder.map(lambda f: coords[f][0] if f in coords else np.nan).round(4), "lon": folder.map(lambda f: coords[f][1] if f in coords else np.nan).round(4),
        "coord_precision_km": 1.0, "site_id": "aad:" + folder, "location_name": folder.map(lambda f: coords[f][2] + " (Southern Ocean mooring)" if f in coords else ""),
        "source": "aad", "source_clip": c.source_record_id, "group": c.file_path.str.rsplit("/", n=1).str[1].str[:15], "max_windows": 1,
        "stem": "aad_" + c.clip_id.astype(str),
    })


# ----------------------------------------------------------------------------- audio


def _resample(x: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    if sr_in == sr_out:
        return x
    g = math.gcd(sr_in, sr_out)
    return resample_poly(x, sr_out // g, sr_in // g)


def _write(path: str, y: np.ndarray, sr: int) -> float:
    """Peak-normalise to 0.9 full scale (records lose resolution in 16-bit otherwise) and return the gain in dB."""
    peak = float(np.abs(y).max())
    gain = 0.9 / peak if peak > 0 else 1.0
    sf.write(path, (y * gain * 32767).astype(np.int16), sr, subtype="PCM_16")
    return round(20 * math.log10(gain), 2)


def process_cuts(job: tuple) -> list[tuple]:
    """Open one original recording once and cut a window centred on every requested time."""
    src, cuts, out_dir, sr, win = job
    rows = []
    try:
        with sf.SoundFile(src) as f:
            sr_in, total = f.samplerate, f.frames
            n_in = int(round(win * sr_in))
            for stem, center in cuts:
                start = int(round(center * sr_in - n_in / 2))
                start = max(0, min(start, total - n_in))
                if start < 0:
                    rows.append((stem, -1, sr_in, 0.0, 0.0, "recording shorter than window")); continue
                f.seek(start)
                x = f.read(n_in, dtype="float32", always_2d=True).mean(axis=1)
                if len(x) < n_in or not np.isfinite(x).all():
                    rows.append((stem, -1, sr_in, 0.0, 0.0, "short or non-finite read")); continue
                y = _resample(x, int(sr_in), sr)
                n = int(round(win * sr))
                y = y[:n] if len(y) >= n else np.pad(y, (0, n - len(y)))
                g = _write(os.path.join(out_dir, f"{stem}_0.wav"), y, sr)
                rows.append((stem, 0, int(sr_in), 0.0, g, ""))
    except Exception as e:
        rows.extend((stem, -1, 0, 0.0, 0.0, f"read error: {e}") for stem, _ in cuts)
    return rows


def process(job: tuple) -> list[tuple]:
    """Read one source clip, write its windows, return (stem, window_idx, orig_sr, pad_s) rows."""
    src, stem, max_windows, out_dir, sr, win = job
    try:
        x, sr_in = sf.read(src, dtype="float32", always_2d=True)
    except Exception as e:  # unreadable file
        return [(stem, -1, 0, 0.0, 0.0, f"read error: {e}")]
    x = x.mean(axis=1)
    if not np.isfinite(x).all() or len(x) == 0:
        return [(stem, -1, sr_in, 0.0, 0.0, "empty or non-finite")]
    x = _resample(x, int(sr_in), sr)
    n = int(round(win * sr))
    rows = []
    if len(x) <= n:
        pad = n - len(x)
        y = np.pad(x, (pad // 2, pad - pad // 2))
        starts, pad_s = [0], pad / sr
        y_all = [y]
    else:
        k = max(1, min(max_windows, len(x) // n))
        starts = np.linspace(0, len(x) - n, k).astype(int)
        y_all, pad_s = [x[s:s + n] for s in starts], 0.0
    for i, y in enumerate(y_all):
        g = _write(os.path.join(out_dir, f"{stem}_{i}.wav"), y, sr)
        rows.append((stem, i, int(sr_in), round(pad_s, 3), g, ""))
    return rows


# ----------------------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=os.environ.get("MARINE_SOUNDS_DB", "~/Projects/marine-sounds-db"))
    ap.add_argument("--out", default="~/Projects/marine-sounds-db/whale-clips")
    ap.add_argument("--sr", type=int, default=8000, help="output sample rate (8000 = Keiko buoy, 2000 = Kaggle)")
    ap.add_argument("--win", type=float, default=2.0, help="clip length in seconds (Kaggle: 2.0)")
    ap.add_argument("--max-watkins", type=int, default=3, help="windows per long Watkins cut")
    ap.add_argument("--neg-per-file", type=int, default=3, help="unannotated negative windows per DCLDE recording")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--limit", type=int, default=0, help="debug: only first N source clips per source")
    ap.add_argument("--csv-copy", default="", help="also write train.csv.gz here (e.g. the repo folder)")
    a = ap.parse_args()
    db_root, out = Path(a.db).expanduser(), Path(a.out).expanduser()
    (out / "train").mkdir(parents=True, exist_ok=True)

    print("collecting source tables", file=sys.stderr)
    tables = [kaggle_table(db_root), watkins_table(db_root), dclde_table(db_root, a.win, a.neg_per_file), aad_table(db_root)]
    if a.limit:
        tables = [t.head(a.limit) for t in tables]
    t = pd.concat(tables, ignore_index=True)
    t["kind"] = t["kind"].fillna("clip") if "kind" in t else "clip"
    t.loc[t.source == "watkins", "max_windows"] = a.max_watkins
    t["split"] = t.group.astype(str).map(split_of)
    t = t[t.src.map(os.path.exists)]
    note("all", "source clips to window", len(t))

    clip_jobs = [(r.src, r.stem, int(r.max_windows), str(out / "train"), a.sr, a.win) for r in t[t.kind == "clip"].itertuples()]
    cut_jobs = [(src, list(zip(g.stem, g.center_s)), str(out / "train"), a.sr, a.win) for src, g in t[t.kind == "cut"].groupby("src")]
    note("all", "original recordings to cut windows from", len(cut_jobs))
    rows = []
    with Pool(a.workers) as pool:
        for i, res in enumerate(pool.imap_unordered(process, clip_jobs, chunksize=64), 1):
            rows.extend(res)
            if i % 10000 == 0:
                print(f"  {i:,}/{len(clip_jobs):,} source clips done", file=sys.stderr)
        for i, res in enumerate(pool.imap_unordered(process_cuts, cut_jobs, chunksize=1), 1):
            rows.extend(res)
            if i % 200 == 0:
                print(f"  {i:,}/{len(cut_jobs):,} recordings cut", file=sys.stderr)
    w = pd.DataFrame(rows, columns=["stem", "w", "orig_sr", "pad_s", "gain_db", "err"])
    bad = w[w.w < 0]
    note("all", "source clips unreadable (skipped)", len(bad))
    w = w[w.w >= 0]
    m = t.set_index("stem").join(w.set_index("stem"), how="inner").reset_index()
    m["clip_name"] = m.stem + "_" + m.w.astype(str) + ".wav"
    m = m[COLS].sort_values("clip_name").reset_index(drop=True)
    assert m.clip_name.is_unique
    m.to_csv(out / "train.csv", index=False)
    if a.csv_copy:
        m.to_csv(Path(a.csv_copy).expanduser() / "train.csv.gz", index=False, compression="gzip")
    note("all", f"clips written ({a.win:g} s, {a.sr} Hz, mono 16-bit)", len(m))

    with open(out / "build_stats.md", "w") as f:
        f.write(f"# whale-clips build\n\nsr={a.sr} Hz, win={a.win} s, max_watkins={a.max_watkins}\n\n| source | step | n |\n|---|---|---:|\n")
        for src, what, n in stats:
            f.write(f"| {src} | {what} | {n:,} |\n")
        f.write("\n## clips per source x label\n\n" + m.groupby(["source", "label", "common_name"]).size().rename("clips").reset_index().to_markdown(index=False) + "\n")
        f.write("\n## split\n\n" + m.groupby(["source", "split"]).size().rename("clips").reset_index().to_markdown(index=False) + "\n")
        if len(bad):
            f.write("\n## unreadable\n\n" + "\n".join(f"- {s}: {e}" for s, e in zip(bad.stem, bad.err)) + "\n")
    if a.csv_copy:
        import shutil
        shutil.copy(out / "build_stats.md", Path(a.csv_copy).expanduser() / "build_stats.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
