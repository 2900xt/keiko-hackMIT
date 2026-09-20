#!/usr/bin/env python3
"""NOAA ISD fixed-width records -> hourly weather CSV.

    python data/parse_isd.py                       # data/noaa_isd/data/*/*.gz -> data/isd_hourly.csv
    python data/parse_isd.py --raw data/isd_obs.csv  # also keep every observation before hourly resampling

Mandatory section (1-based positions, ISD format document): station 5-15, date 16-23, time 24-27 UTC, wind dir 61-63 +
qc 64, wind speed 66-69 (m/s x10) + qc 70, ceiling 71-75, visibility 79-84 (m), temp 88-92 (C x10) + qc 93, dew point
94-98 + qc 99, sea-level pressure 100-104 (hPa x10) + qc 105. Additional data: 'AA1' = liquid precip: period (h, 2),
depth (mm x10, 4), condition (1), qc (1). All-9s = missing. QC codes 3 and 7 = erroneous, dropped.
"""
import argparse, gzip, pathlib, re, sys
import numpy as np, pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
BAD_QC = {"3", "7"}
AA1 = re.compile(r"AA1(\d{2})(\d{4})(\d)(\d)")

def field(line, a, b, missing, scale=1.0, qc=None):
    raw = line[a - 1:b]
    if not raw.strip() or set(raw.strip("+-")) == {"9"} or (qc and line[qc - 1] in BAD_QC): return np.nan
    try: return int(raw) / scale
    except ValueError: return np.nan

def parse_line(line):
    if len(line) < 105: return None
    precip_h = precip_mm = np.nan
    m = AA1.search(line[105:])
    if m and m.group(4) not in BAD_QC and m.group(2) != "9999":
        precip_h, precip_mm = int(m.group(1)), int(m.group(2)) / 10
    return dict(
        station=f"{line[4:10]}-{line[10:15]}", ts=f"{line[15:23]}T{line[23:27]}",
        wind_dir_deg=field(line, 61, 63, 999, qc=64), wind_ms=field(line, 66, 69, 9999, 10, qc=70),
        ceiling_m=field(line, 71, 75, 99999), visibility_m=field(line, 79, 84, 999999),
        temp_c=field(line, 88, 92, 9999, 10, qc=93), dewpoint_c=field(line, 94, 98, 9999, 10, qc=99),
        slp_hpa=field(line, 100, 104, 99999, 10, qc=105), precip_period_h=precip_h, precip_mm=precip_mm)

def read_files(paths):
    rows = []
    for p in paths:
        with gzip.open(p, "rt", errors="replace") as f:
            rows += [r for r in map(parse_line, f) if r]
        print(f"{p.name}: {len(rows)} obs so far", file=sys.stderr)
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df.ts, format="%Y%m%dT%H%M", utc=True)
    return df.sort_values(["station", "ts"])

def hourly(df):
    """Mean of the numeric fields per station-hour; precip is converted to an hourly rate (mm/h) before averaging."""
    df = df.copy(); df["precip_mm_h"] = df.precip_mm / df.precip_period_h.replace(0, np.nan)
    df["hour"] = df.ts.dt.floor("h")
    num = ["wind_dir_deg", "wind_ms", "ceiling_m", "visibility_m", "temp_c", "dewpoint_c", "slp_hpa", "precip_mm_h"]
    h = df.groupby(["station", "hour"])[num].mean().reset_index().rename(columns={"hour": "ts"})
    h["wind_dir_deg"] = df.groupby(["station", "hour"]).apply(_circular_mean_dir, include_groups=False).values
    h["n_obs"] = df.groupby(["station", "hour"]).size().values
    # 3-hour pressure tendency, the number forecasters look at
    h["slp_tendency_hpa_3h"] = h.groupby("station").slp_hpa.diff(3)
    return h

def _circular_mean_dir(g):
    d = np.deg2rad(g.wind_dir_deg.dropna())
    return np.nan if d.empty else float(np.rad2deg(np.arctan2(np.sin(d).mean(), np.cos(d).mean())) % 360)

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--isd-dir", type=pathlib.Path, default=HERE / "noaa_isd" / "data")
    ap.add_argument("--out", type=pathlib.Path, default=HERE / "isd_hourly.csv")
    ap.add_argument("--raw", type=pathlib.Path, help="also write every observation (pre-resample) here")
    a = ap.parse_args()
    paths = sorted(a.isd_dir.glob("*/*.gz"))
    if not paths: sys.exit(f"no .gz files under {a.isd_dir}; run data/fetch_isd.sh first")
    obs = read_files(paths)
    if a.raw: obs.to_csv(a.raw, index=False)
    h = hourly(obs); h.to_csv(a.out, index=False)
    print(f"{len(obs)} observations -> {len(h)} station-hours, {h.ts.min()} .. {h.ts.max()} -> {a.out}")
    print(h.describe().T[["count", "mean", "min", "max"]].to_string())

if __name__ == "__main__": main()
