#!/usr/bin/env python3
"""Build a clean whale-occurrence table for a location / presence model.

Every row in the output is a real whale detection with a known sensor position and a
timestamp. Three sources survive triage (see README.md for what was dropped and why):

  watkins   Watkins Marine Mammal Sound Database (WHOI). Species + date + position per
            recording. Positions come from the record (whole degrees) or, when the
            recordist wrote them in the notes ("N42 14' W070 02'"), parsed to minutes.
  dclde     DCLDE 2027 killer-whale dataset (Palmer et al. 2025, Sci Data). Per-call UTC
            timestamps at fixed hydrophones in WA / BC / AK. Site coordinates are from the
            paper's deployment table (Table 1). DFO sites have no published position and
            are dropped.
  aad       IWC-SORP / AAD Antarctic blue & fin whale annotated library. Per-call UTC
            timestamps at 10 moorings around Antarctica; positions from the library's own
            01-Documentation/folderStructure.csv.

Usage:
  python3 build_whale_locations.py [--db ~/Projects/marine-sounds-db] [--out .]

Outputs (in --out):
  whale_locations.csv       one row per detection event (Watkins: per recording-day;
                            DCLDE / AAD: per site x species x UTC minute)
  whale_presence_daily.csv  site x species x date with detection counts
  sites.csv                 sensor registry with coordinates and positional precision
  build_report.md           kept / dropped counts per source and reason
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------------- config

CETACEAN_GROUPS = {"baleen whale", "toothed whale"}

# Watkins recordings made in captivity carry no wild-location signal.
CAPTIVE_RX = re.compile(
    r"aquarium|marineland|marine land|seaquarium|sea ?world|\btank\b|\bzoo\b|silver springs|"
    r"canal 13|johns hopkins|oceanarium|niag[a]?ra|\bpool\b|\blab(?:oratory)?\b|holding pen|\bpen\b",
    re.I,
)

# DCLDE 2027 deployment table (Palmer et al. 2025, Sci Data 12, Table 1). Two-decimal
# coordinates, so positional precision is ~1 km. UAF codes carry an instrument serial
# after the site prefix; the prefix maps to the bay / strait in the table.
DCLDE_SITES = {
    # code            (name,                              lat,    lon,      precision_km, provider)
    "HaroStraitNorth": ("Haro Strait Northbound",          48.52, -123.19, 1, "JASCO_VFPA"),
    "HaroStraitSouth": ("Haro Strait Southbound",          48.52, -123.21, 1, "JASCO_VFPA"),
    "BoundaryPass":    ("Boundary Pass",                   48.76, -123.07, 1, "JASCO_VFPA"),
    "StraitofGeorgia": ("Strait of Georgia (ONC node)",    49.04, -123.32, 1, "JASCO_VFPA_ONC"),
    "LimeKiln":        ("Lime Kiln Point, San Juan Island", 48.51, -123.15, 1, "SMRUConsulting"),
    "BarkleyCanyon":   ("Barkley Canyon (ONC)",            48.43, -126.17, 1, "ONC"),
    "orcasound_lab":   ("Orcasound Lab, Haro Strait",      48.52, -123.16, 1, "OrcaSound"),
    "bush_point":      ("Bush Point, Whidbey Island",      48.03, -122.61, 1, "OrcaSound"),
    "port_townsend":   ("Port Townsend",                   48.14, -122.76, 1, "OrcaSound"),
    "Cpe_Elz":         ("Cape Elizabeth HARP",             47.36, -124.68, 1, "SIO"),
    "Quin_Can":        ("Quinault Canyon HARP",            47.50, -125.35, 1, "SIO"),
    "Tekteksen":       ("Tekteksen, Saturna Island",       48.78, -123.05, 1, "SIMRES"),
}
DCLDE_UAF_PREFIX = {
    # prefix   (name,                               lat,    lon,      precision_km)
    "HE":    ("Hinchinbrook Entrance, PWS",          60.31, -146.97, 5),
    "KB":    ("Kachemak Bay",                        59.88, -151.85, 5),
    "MS":    ("Montague Strait, PWS",                60.18, -147.82, 5),
    "RB":    ("Resurrection Bay",                    59.73, -149.53, 5),
    "Field": ("Kenai Fjords / Prince William Sound (vessel-based)", 60.15, -147.59, 50),
}
DCLDE_SPECIES = {
    "KW": ("Orcinus orca", "Killer whale", "toothed whale"),
    "HW": ("Megaptera novaeangliae", "Humpback whale", "baleen whale"),
}

AAD_CALLS = [  # (regex on selection-file name, species, common, call type)
    (r"ant[-_ ]?a", "Balaenoptera musculus intermedia", "Antarctic blue whale", "Bm-Ant-A"),
    (r"ant[-_ ]?b", "Balaenoptera musculus intermedia", "Antarctic blue whale", "Bm-Ant-B"),
    (r"ant[-_ ]?z", "Balaenoptera musculus intermedia", "Antarctic blue whale", "Bm-Ant-Z"),
    (r"bm[._ ]?d|dcalls", "Balaenoptera musculus intermedia", "Antarctic blue whale", "Bm-D"),
    (r"20plus", "Balaenoptera physalus", "Fin whale", "Bp-20Plus"),
    (r"20hz|bp[._]?20\b|fin[._]20hz", "Balaenoptera physalus", "Fin whale", "Bp-20Hz"),
    (r"downsweep|dwnswp|dswp|fin[._]ds|bp[._]ds", "Balaenoptera physalus", "Fin whale", "Bp-Downsweep"),
]

# ----------------------------------------------------------------------------- helpers

report: list[tuple[str, str, int]] = []


def note(source: str, what: str, n: int) -> None:
    report.append((source, what, int(n)))
    print(f"  {source:8s} {what:<58s} {n:>8,d}", file=sys.stderr)


# A hemisphere letter that is not part of a word, followed by 1–2 numbers written in any of the
# Watkins conventions: N42 14', N42 14.6', N39' 45, N32'21, N15 13.92, S77.48, W156.
_COORD_TOKEN = re.compile(
    r"(?<![A-Za-z])([NSEW])\s*'?\s*(\d{1,3}(?:\.\d+)?)\s*[°º']?\s*'?\s*(\d{1,2}(?:\.\d+)?)?'?"
)


def _token_to_deg(letter: str, a: str, b: str | None) -> float | None:
    """Return signed decimal degrees, or None if the token is not a plausible coordinate."""
    if b is None:
        if "." in a:                       # "S77.48" — degrees.minutes in the Watkins notes
            d, frac = a.split(".")
            deg, minutes = float(d), float(frac[:2].ljust(2, "0"))
        else:
            deg, minutes = float(a), 0.0
    else:
        if "." in a:                       # "N42.3 15" is not a format we trust
            return None
        deg, minutes = float(a), float(b)
    limit = 90 if letter in "NS" else 180
    if not (0 <= deg <= limit and 0 <= minutes < 60):
        return None
    val = deg + minutes / 60
    return -val if letter in "SW" else val


def parse_note_coords(text: str) -> tuple[float, float] | None:
    """Pull a lat/lon pair out of a Watkins recordist note, if one is written there."""
    if not text:
        return None
    lat = lon = None
    lat_end = None
    for m in _COORD_TOKEN.finditer(text):
        letter, a, b = m.group(1), m.group(2), m.group(3)
        val = _token_to_deg(letter, a, b)
        if val is None:
            continue
        if letter in "NS" and lat is None:
            lat, lat_end = val, m.end()
        elif letter in "EW" and lat is not None and lon is None and m.start() - lat_end <= 12:
            lon = val
            break
    if lat is None or lon is None:
        return None
    return lat, lon


def minute_floor(ts: pd.Series) -> pd.Series:
    return ts.dt.floor("min")


# ----------------------------------------------------------------------------- sources


def watkins_clips(db_root: Path) -> pd.DataFrame:
    """Cleaned clip-level Watkins table: cetaceans, wild, dated, positioned. Shared with build_whale_clips.py."""
    con = sqlite3.connect(db_root / "marine_sounds.sqlite")
    df = pd.read_sql(
        """
        SELECT c.clip_id, c.source_record_id, s.scientific_name, s.common_name, s.taxon_group,
               c.sound_type, c.observation_date, c.location, c.lat, c.lon, c.note, c.file_path, c.sample_rate, c.duration_s
        FROM clips c JOIN datasets d USING (dataset_id) LEFT JOIN species s USING (species_id)
        WHERE d.name LIKE 'Watkins%'
        """,
        con,
    )
    con.close()
    note("watkins", "clips in catalogue", len(df))

    m = df.taxon_group.isin(CETACEAN_GROUPS)
    note("watkins", "dropped: not a cetacean (seals, sea otter, unlabeled)", (~m).sum())
    df = df[m]

    m = df.location.fillna("").str.contains(CAPTIVE_RX)
    note("watkins", "dropped: captive recording (aquarium, tank, zoo)", m.sum())
    df = df[~m]

    df = df.assign(date=pd.to_datetime(df.observation_date, errors="coerce", utc=True))
    m = df.date.isna()
    note("watkins", "dropped: no recording date", m.sum())
    df = df[~m]
    m = ~df.date.dt.year.between(1940, 2010)
    note("watkins", "dropped: implausible date (outside 1940-2010)", m.sum())
    df = df[~m]

    # Position: prefer coordinates written in the note (minute precision), cross-checked
    # against the whole-degree record position when one exists.
    parsed = df.note.fillna("").map(parse_note_coords)
    p_lat = parsed.map(lambda t: t[0] if t else np.nan)
    p_lon = parsed.map(lambda t: t[1] if t else np.nan)
    has_rec = df.lat.notna() & df.lon.notna()
    agree = has_rec & ((p_lat - df.lat).abs() <= 2) & ((p_lon - df.lon).abs() <= 2)
    use_note = p_lat.notna() & (agree | ~has_rec)
    note("watkins", "position parsed from recordist note (minute precision)", use_note.sum())
    note("watkins", "note position rejected (disagrees with record by >2 deg)", (p_lat.notna() & has_rec & ~agree).sum())

    df = df.assign(
        lat_out=np.where(use_note, p_lat, df.lat),
        lon_out=np.where(use_note, p_lon, df.lon),
        coord_source=np.where(use_note, "watkins_note_degmin", np.where(has_rec, "watkins_record_whole_degree", "none")),
        coord_precision_km=np.where(use_note, 2, np.where(has_rec, 60, np.nan)),
    )
    m = df.lat_out.isna() | df.lon_out.isna()
    note("watkins", "dropped: no position at all", m.sum())
    df = df[~m]
    m = df.lat_out.abs().gt(90) | df.lon_out.abs().gt(180) | ((df.lat_out == 0) & (df.lon_out == 0))
    note("watkins", "dropped: position out of range", m.sum())
    df = df[~m]
    note("watkins", "clips kept", len(df))
    return df


def load_watkins(db_root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = watkins_clips(db_root)
    # One event per species x day x position. Many cuts come from the same tape.
    df["day"] = df.date.dt.floor("D")
    g = (
        df.groupby(["scientific_name", "common_name", "taxon_group", "day", "lat_out", "lon_out", "coord_source", "coord_precision_km"], dropna=False)
        .agg(
            n_detections=("clip_id", "size"),
            call_type=("sound_type", lambda s: ";".join(sorted({t for v in s.dropna() for t in str(v).split(";") if t}))[:120]),
            location_name=("location", lambda s: s.dropna().mode().iat[0] if s.dropna().size else ""),
            source_ref=("source_record_id", lambda s: ",".join(s.astype(str).head(3)) + (",..." if len(s) > 3 else "")),
        )
        .reset_index()
    )
    events = pd.DataFrame(
        {
            "source": "watkins",
            "site_id": "watkins:" + g.lat_out.round(3).astype(str) + "," + g.lon_out.round(3).astype(str),
            "location_name": g.location_name.str.strip().str.rstrip("OX ;"),
            "lat": g.lat_out.round(4),
            "lon": g.lon_out.round(4),
            "coord_precision_km": g.coord_precision_km,
            "coord_source": g.coord_source,
            "datetime_utc": g.day.dt.strftime("%Y-%m-%dT00:00:00Z"),
            "time_precision": "day",
            "species": g.scientific_name,
            "common_name": g.common_name,
            "taxon_group": g.taxon_group,
            "ecotype": "",
            "call_type": g.call_type,
            "n_detections": g.n_detections,
            "source_ref": g.source_ref,
        }
    )
    note("watkins", "events (species x day x position)", len(events))
    sites = events.groupby("site_id").agg(lat=("lat", "first"), lon=("lon", "first"), coord_precision_km=("coord_precision_km", "first"), name=("location_name", "first")).reset_index()
    sites["source"] = "watkins"
    sites["provider"] = "WHOI Watkins"
    return events, sites


def _dclde_site(code: str):
    if code in DCLDE_SITES:
        name, lat, lon, prec, prov = DCLDE_SITES[code]
        return code, name, lat, lon, prec, prov
    prefix = code.split("_")[0]
    if prefix in DCLDE_UAF_PREFIX:
        name, lat, lon, prec = DCLDE_UAF_PREFIX[prefix]
        return code, name, lat, lon, prec, "UAF_NGOS"
    return None


def load_dclde(db_root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    path = db_root / "raw/dclde2027_kw/Annotations.csv"
    a = pd.read_csv(path, usecols=["Soundfile", "Dataset", "Provider", "UTC", "ClassSpecies", "KW_certain", "Ecotype"], low_memory=False, dtype={"Ecotype": str})
    note("dclde", "annotations in Annotations.csv", len(a))

    m = a.ClassSpecies.isin(DCLDE_SPECIES)
    note("dclde", "dropped: not a whale (abiotic, undetermined biological)", (~m).sum())
    a = a[m]
    m = a.KW_certain.eq(0)
    note("dclde", "dropped: annotator flagged killer whale as uncertain", m.sum())
    a = a[~m]

    site = a.Dataset.map(_dclde_site)
    m = site.isna()
    note("dclde", "dropped: hydrophone position unpublished (DFO sites)", m.sum())
    a = a[~m]
    site = site[~m]

    a = a.assign(ts=pd.to_datetime(a.UTC, errors="coerce", utc=True, format="mixed"))
    m = a.ts.isna()
    note("dclde", "dropped: unparseable UTC", m.sum())
    a = a[~m]
    site = site[~m]

    a = a.assign(
        site_code=site.map(lambda t: t[0]), site_name=site.map(lambda t: t[1]), lat=site.map(lambda t: t[2]),
        lon=site.map(lambda t: t[3]), prec=site.map(lambda t: t[4]), provider=site.map(lambda t: t[5]),
        species=a.ClassSpecies.map(lambda k: DCLDE_SPECIES[k][0]), common=a.ClassSpecies.map(lambda k: DCLDE_SPECIES[k][1]),
        group=a.ClassSpecies.map(lambda k: DCLDE_SPECIES[k][2]), ecotype=a.Ecotype.fillna(""), minute=minute_floor(a.ts),
    )
    note("dclde", "annotations kept", len(a))
    g = a.groupby(["site_code", "site_name", "lat", "lon", "prec", "provider", "species", "common", "group", "ecotype", "minute"]).agg(
        n_detections=("UTC", "size"), source_ref=("Soundfile", "first")
    ).reset_index()
    events = pd.DataFrame(
        {
            "source": "dclde", "site_id": "dclde:" + g.site_code, "location_name": g.site_name, "lat": g.lat, "lon": g.lon,
            "coord_precision_km": g.prec, "coord_source": "dclde_deployment_table", "datetime_utc": g.minute.dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "time_precision": "minute", "species": g.species, "common_name": g.common, "taxon_group": g.group, "ecotype": g.ecotype,
            "call_type": "", "n_detections": g.n_detections, "source_ref": g.source_ref,
        }
    )
    note("dclde", "events (site x species x ecotype x minute)", len(events))
    sites = g.groupby("site_code").agg(lat=("lat", "first"), lon=("lon", "first"), coord_precision_km=("prec", "first"), name=("site_name", "first"), provider=("provider", "first")).reset_index()
    sites["site_id"] = "dclde:" + sites.site_code
    sites["source"] = "dclde"
    return events, sites[["site_id", "lat", "lon", "coord_precision_km", "name", "source", "provider"]]


def _aad_call(fname: str):
    low = fname.lower()
    for rx, sp, common, ct in AAD_CALLS:
        if re.search(rx, low):
            return sp, common, ct
    return None


def load_aad(db_root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    base = db_root / "raw/aad_bluefin"
    fs = pd.read_csv(base / "01-Documentation/folderStructure.csv")
    rows = []
    n_files = n_unid = 0
    for _, r in fs.iterrows():
        folder = base / str(r.Folder).replace("\\", "").strip("/")
        if not folder.is_dir():
            print(f"  aad      missing folder {folder}", file=sys.stderr)
            continue
        for f in sorted(glob.glob(str(folder / "*.txt"))):
            if "backbeat" in f.lower():
                continue
            call = _aad_call(Path(f).name)
            if call is None:  # Unidentified / unknown call tables
                n_unid += sum(1 for _ in open(f, errors="replace")) - 1
                continue
            n_files += 1
            t = pd.read_csv(f, sep="\t", low_memory=False, on_bad_lines="skip", encoding_errors="replace")
            t.columns = [c.strip().lower() for c in t.columns]
            col = next((c for c in t.columns if c.startswith("begin date time")), None)
            if col is None:
                print(f"  aad      no 'Begin Date Time' in {Path(f).name}; skipped", file=sys.stderr)
                continue
            rows.append(pd.DataFrame({
                "site_code": str(r.SiteCode), "folder": Path(folder).name, "lat": float(r.Latitude), "lon": float(r.Longitude),
                "raw_time": t[col].astype(str), "species": call[0], "common": call[1], "call_type": call[2], "source_ref": Path(f).name,
            }))
    a = pd.concat(rows, ignore_index=True)
    note("aad", f"annotations read from {n_files} Raven selection tables", len(a))
    note("aad", "dropped: 'unidentified call' tables (no species)", n_unid)
    a["ts"] = pd.to_datetime(a.raw_time.str.replace(r"\s+", " ", regex=True).str.strip(), errors="coerce", utc=True, format="mixed")
    m = a.ts.isna()
    note("aad", "dropped: unparseable Begin Date Time", m.sum())
    a = a[~m]
    m = ~a.ts.dt.year.between(2004, 2019)
    note("aad", "dropped: timestamp outside deployment years", m.sum())
    a = a[~m]
    a["minute"] = minute_floor(a.ts)
    note("aad", "annotations kept", len(a))
    g = a.groupby(["site_code", "folder", "lat", "lon", "species", "common", "call_type", "minute"]).agg(n_detections=("raw_time", "size"), source_ref=("source_ref", "first")).reset_index()
    events = pd.DataFrame(
        {
            "source": "aad", "site_id": "aad:" + g.folder, "location_name": g.site_code + " (Southern Ocean mooring)", "lat": g.lat.round(4), "lon": g.lon.round(4),
            "coord_precision_km": 1, "coord_source": "aad_folderStructure", "datetime_utc": g.minute.dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "time_precision": "minute", "species": g.species, "common_name": g.common, "taxon_group": "baleen whale", "ecotype": "",
            "call_type": g.call_type, "n_detections": g.n_detections, "source_ref": g.source_ref,
        }
    )
    note("aad", "events (site x species x call type x minute)", len(events))
    sites = events.groupby("site_id").agg(lat=("lat", "first"), lon=("lon", "first"), coord_precision_km=("coord_precision_km", "first"), name=("location_name", "first")).reset_index()
    sites["source"] = "aad"
    sites["provider"] = "AAD / IWC-SORP"
    return events, sites


# ----------------------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=os.environ.get("MARINE_SOUNDS_DB", "~/Projects/marine-sounds-db"), help="marine-sounds-db root (has marine_sounds.sqlite and raw/)")
    ap.add_argument("--out", default=str(Path(__file__).parent), help="output folder")
    a = ap.parse_args()
    db_root, out = Path(a.db).expanduser(), Path(a.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)

    print("building whale location table", file=sys.stderr)
    ev_w, s_w = load_watkins(db_root)
    ev_d, s_d = load_dclde(db_root)
    ev_a, s_a = load_aad(db_root)

    cols = ["event_id", "source", "site_id", "location_name", "lat", "lon", "coord_precision_km", "coord_source", "datetime_utc", "time_precision",
            "species", "common_name", "taxon_group", "ecotype", "call_type", "n_detections", "source_ref"]
    ev = pd.concat([ev_w, ev_d, ev_a], ignore_index=True)
    ev["event_id"] = np.arange(1, len(ev) + 1)
    ev = ev[cols].sort_values(["source", "site_id", "datetime_utc", "species"]).reset_index(drop=True)
    ev["event_id"] = np.arange(1, len(ev) + 1)
    assert ev.lat.between(-90, 90).all() and ev.lon.between(-180, 180).all()
    assert ev.datetime_utc.str.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$").all()
    assert ev.species.notna().all()
    ev.to_csv(out / "whale_locations.csv", index=False)
    note("all", "events written to whale_locations.csv", len(ev))

    d = ev.assign(date=ev.datetime_utc.str[:10])
    daily = d.groupby(["source", "site_id", "lat", "lon", "coord_precision_km", "date", "species", "common_name", "taxon_group"]).agg(
        n_detections=("n_detections", "sum"), n_events=("event_id", "size"), ecotypes=("ecotype", lambda s: ";".join(sorted({x for x in s if x})))
    ).reset_index()
    daily.to_csv(out / "whale_presence_daily.csv", index=False)
    note("all", "site x species x day rows in whale_presence_daily.csv", len(daily))

    sites = pd.concat([s_w, s_d, s_a], ignore_index=True)[["site_id", "source", "provider", "name", "lat", "lon", "coord_precision_km"]]
    sites.to_csv(out / "sites.csv", index=False)

    with open(out / "build_report.md", "w") as f:
        f.write("# build report\n\nGenerated by build_whale_locations.py. Counts are rows at each step.\n\n| source | step | n |\n|---|---|---:|\n")
        for src, what, n in report:
            f.write(f"| {src} | {what} | {n:,} |\n")
        f.write("\n## events per source and species\n\n")
        f.write(ev.groupby(["source", "common_name"]).agg(events=("event_id", "size"), detections=("n_detections", "sum"), sites=("site_id", "nunique"),
                first=("datetime_utc", "min"), last=("datetime_utc", "max")).to_markdown())
        f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
