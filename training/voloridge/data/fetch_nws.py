#!/usr/bin/env python3
"""Recent observations from the NWS API for the same ASOS station ISD archives -> the isd_hourly.csv schema.

    python data/fetch_nws.py                          # KBOS, last 7 days -> data/nws_hourly.csv
    python data/fetch_nws.py --start 2026-09-18T00:00Z --end 2026-09-21T00:00Z --merge

Why: the public ISD archive (s3://noaa-isd-pds and ncei.noaa.gov) lags — as of 2026-09-20 the latest Logan record is
2025-08-27. ISD *is* the archive of the ASOS/METAR reports that api.weather.gov serves live, so for recordings made
this week the NWS feed is the same instrument, hours old instead of a year. Fields are mapped onto parse_isd.py's
columns (wind_ms, wind_dir_deg, temp_c, dewpoint_c, slp_hpa, visibility_m, precip_mm_h, slp_tendency_hpa_3h) and
averaged to the hour, so analysis/join_isd.py doesn't care which source a row came from (`source` column says).
--merge appends to data/isd_hourly.csv (dedup on station+ts, NWS wins for overlapping hours).
"""
import argparse, pathlib, sys, time, urllib.parse, urllib.request, json
import numpy as np, pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
STATION_ICAO = {"725090-14739": "KBOS"}
UA = "keiko-hackmit-voloridge (github.com/2900xt/keiko-hackMIT)"

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/geo+json"})
    for i in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r: return json.load(r)
        except Exception as e:
            if i == 3: raise
            time.sleep(2 ** i)

def val(p, k):
    v = p.get(k) or {}; return np.nan if v.get("value") is None else float(v["value"])

def fetch(icao, start, end):
    url = f"https://api.weather.gov/stations/{icao}/observations?" + urllib.parse.urlencode({"start": start, "end": end, "limit": 500})
    rows = []
    while url:
        d = get(url)
        for f in d.get("features", []):
            p = f["properties"]
            rows.append(dict(ts=p["timestamp"], wind_ms=val(p, "windSpeed") / 3.6, wind_dir_deg=val(p, "windDirection"),
                             temp_c=val(p, "temperature"), dewpoint_c=val(p, "dewpoint"), slp_hpa=val(p, "seaLevelPressure") / 100, ceiling_m=np.nan,
                             visibility_m=val(p, "visibility"), precip_mm=val(p, "precipitationLastHour") * 1000, precip_period_h=1.0))
        url = d.get("pagination", {}).get("next") if d.get("features") else None
    df = pd.DataFrame(rows)
    if df.empty: return df
    df["ts"] = pd.to_datetime(df.ts, utc=True); return df.sort_values("ts").drop_duplicates("ts")

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--station", default="725090-14739"); ap.add_argument("--icao", help="override the USAF-WBAN -> ICAO map")
    ap.add_argument("--start", help="ISO UTC; default 7 days ago"); ap.add_argument("--end", help="ISO UTC; default now")
    ap.add_argument("--out", type=pathlib.Path, default=HERE / "nws_hourly.csv")
    ap.add_argument("--merge", action="store_true", help="also merge into data/isd_hourly.csv")
    a = ap.parse_args()
    icao = a.icao or STATION_ICAO.get(a.station) or sys.exit(f"no ICAO known for {a.station}; pass --icao")
    iso = lambda t: pd.Timestamp(t).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ") if pd.Timestamp(t).tzinfo else pd.Timestamp(t, tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ")
    now = pd.Timestamp.now("UTC").floor("min"); start = iso(a.start or now - pd.Timedelta(days=7)); end = iso(a.end or now)
    obs = fetch(icao, start, end)
    if obs.empty: sys.exit(f"no observations for {icao} in {start}..{end}")
    sys.path.insert(0, str(HERE)); from parse_isd import hourly  # noqa: E402
    obs["station"] = a.station; h = hourly(obs); h["source"] = "nws"
    h.to_csv(a.out, index=False)
    print(f"{len(obs)} obs from {icao} {obs.ts.min()} .. {obs.ts.max()} -> {len(h)} hours -> {a.out}")
    if a.merge:
        isd_p = HERE / "isd_hourly.csv"
        if isd_p.exists():
            isd = pd.read_csv(isd_p, parse_dates=["ts"]); isd["source"] = isd.get("source", "isd")
            both = pd.concat([isd, h]).sort_values(["station", "ts"]).drop_duplicates(["station", "ts"], keep="last")
        else: both = h
        both.to_csv(isd_p, index=False); print(f"merged -> {isd_p}: {len(both)} station-hours, {both.source.value_counts().to_dict()}")

if __name__ == "__main__": main()
