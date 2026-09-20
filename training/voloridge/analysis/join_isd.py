#!/usr/bin/env python3
"""Join the buoy's hourly noise floor to NOAA ISD hourly weather at Logan and measure how much weather explains.

    python analysis/join_isd.py                 # analysis/out/noise_floor_hourly.csv x data/isd_hourly.csv
    python analysis/join_isd.py --station 725090-14739 --max-gap-h 1

Outputs in analysis/out/: noise_vs_weather.csv (joined rows), summary.json (Spearman rho + p for floor vs wind /
precip / pressure tendency / visibility, an OLS fit floor ~ wind + precip + hour-of-day, its R^2, and the R^2 of
hour-of-day alone so boat traffic isn't mistaken for weather), noise_vs_weather.png (four panels).

Join rule: nearest ISD hour within --max-gap-h of each buoy-hour (Logan reports at :54 past, sometimes more often;
parse_isd.py already averaged to the hour). Everything is UTC.
"""
import argparse, json, pathlib, sys
import numpy as np, pandas as pd
from scipy import stats

HERE = pathlib.Path(__file__).resolve().parent; VOLO = HERE.parent
WEATHER = ["wind_ms", "precip_mm_h", "slp_hpa", "slp_tendency_hpa_3h", "visibility_m", "temp_c"]

def ols_r2(y, X):
    X = np.column_stack([np.ones(len(y)), X]); beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return float(1 - ((y - X @ beta) ** 2).sum() / ((y - y.mean()) ** 2).sum()), beta

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--noise", type=pathlib.Path, default=HERE / "out" / "noise_floor_hourly.csv")
    ap.add_argument("--isd", type=pathlib.Path, default=VOLO / "data" / "isd_hourly.csv")
    ap.add_argument("--station", default="725090-14739"); ap.add_argument("--max-gap-h", type=float, default=1.0)
    ap.add_argument("--out-dir", type=pathlib.Path, default=HERE / "out"); ap.add_argument("--no-plot", action="store_true")
    a = ap.parse_args(); a.out_dir.mkdir(parents=True, exist_ok=True)
    for p in (a.noise, a.isd):
        if not p.exists(): sys.exit(f"missing {p} — run `make noise-floor` / `make isd isd-parse` first")
    noise = pd.read_csv(a.noise, parse_dates=["ts"]); isd = pd.read_csv(a.isd, parse_dates=["ts"])
    isd = isd[isd.station == a.station].sort_values("ts"); noise = noise.sort_values("ts")
    if isd.empty: sys.exit(f"no rows for station {a.station} in {a.isd}")
    df = pd.merge_asof(noise, isd, on="ts", direction="nearest", tolerance=pd.Timedelta(hours=a.max_gap_h), suffixes=("", "_isd"))
    df = df.dropna(subset=["wind_ms"]); df["precip_mm_h"] = df.precip_mm_h.fillna(0.0); df["hour_utc"] = df.ts.dt.hour
    df["hour_local"] = (df.ts.dt.tz_convert("America/New_York") if df.ts.dt.tz is not None else df.ts.dt.tz_localize("UTC").dt.tz_convert("America/New_York")).dt.hour
    df.to_csv(a.out_dir / "noise_vs_weather.csv", index=False)
    n = len(df); print(f"{n} joined buoy-hours ({len(noise)} noise hours, {len(isd)} ISD hours, station {a.station})")
    if n < 4: sys.exit("too few joined hours to correlate — record more, or widen --max-gap-h")

    summary = {"station": a.station, "n_hours": n, "ts_min": str(df.ts.min()), "ts_max": str(df.ts.max()), "spearman": {}}
    for w in WEATHER:
        s = df[["floor_db", w]].dropna()
        if len(s) >= 4 and s[w].nunique() > 1:
            rho, p = stats.spearmanr(s.floor_db, s[w]); summary["spearman"][w] = {"rho": float(rho), "p": float(p), "n": len(s)}
            print(f"  floor_db vs {w:22s} rho={rho:+.2f}  p={p:.3f}  n={len(s)}")
    # how much is weather vs the daily boat cycle?
    hod = np.column_stack([np.sin(2 * np.pi * df.hour_local / 24), np.cos(2 * np.pi * df.hour_local / 24)])
    r2_hod, _ = ols_r2(df.floor_db.values, hod)
    r2_wx, _ = ols_r2(df.floor_db.values, df[["wind_ms", "precip_mm_h"]].values)
    r2_both, beta = ols_r2(df.floor_db.values, np.column_stack([df[["wind_ms", "precip_mm_h"]].values, hod]))  # coefficients net of the daily cycle
    summary["ols"] = {"r2_hour_of_day": r2_hod, "r2_wind_precip": r2_wx, "r2_both": r2_both, "r2_weather_beyond_hour": r2_both - r2_hod,
                      "db_per_m_s_wind": float(beta[1]), "db_per_mm_h_precip": float(beta[2])}
    print(f"  R^2 hour-of-day {r2_hod:.2f} | wind+precip {r2_wx:.2f} | both {r2_both:.2f}  ->  weather adds {r2_both - r2_hod:+.2f}")
    print(f"  {beta[1]:+.2f} dB per m/s of wind, {beta[2]:+.2f} dB per mm/h of rain")
    json.dump(summary, open(a.out_dir / "summary.json", "w"), indent=1)

    if not a.no_plot:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        fig, ax = plt.subplots(2, 2, figsize=(11, 8))
        ax[0, 0].plot(df.ts, df.floor_db, ".-", label="noise floor (dB rel)"); ax2 = ax[0, 0].twinx(); ax2.plot(df.ts, df.wind_ms, "-", c="tab:orange", alpha=.7, label="wind m/s")
        ax[0, 0].set_title("noise floor and Logan wind"); ax[0, 0].tick_params(axis="x", rotation=30); ax[0, 0].legend(loc="upper left"); ax2.legend(loc="upper right")
        ax[0, 1].scatter(df.wind_ms, df.floor_db, c=df.precip_mm_h > 0, cmap="coolwarm", s=18); ax[0, 1].set_xlabel("wind m/s"); ax[0, 1].set_ylabel("floor dB"); ax[0, 1].set_title("floor vs wind (red = raining)")
        ax[1, 0].scatter(df.slp_tendency_hpa_3h, df.floor_db, s=18); ax[1, 0].set_xlabel("3 h pressure tendency hPa"); ax[1, 0].set_ylabel("floor dB"); ax[1, 0].set_title("floor vs pressure tendency")
        df.groupby("hour_local").floor_db.median().plot(ax=ax[1, 1], marker="o"); ax[1, 1].set_xlabel("hour (local)"); ax[1, 1].set_title("diurnal cycle (boats)")
        fig.suptitle(f"Keiko noise floor x NOAA ISD {a.station}, n={n} h"); fig.tight_layout(); fig.savefig(a.out_dir / "noise_vs_weather.png", dpi=130)
        print("plot ->", a.out_dir / "noise_vs_weather.png")

if __name__ == "__main__": main()
