# Voloridge — Signal in the Noise

Keiko's training + analysis track for the Voloridge challenge. Two things happen here:

1. **Train on Voloridge compute.** The whale CNN pretrains on the 30k+ clip public corpus (Watkins, Cornell/Kaggle,
   NOAA, ReefSet, ...) on a Voloridge AWS GPU instance, then fine-tunes on our own Charles River / Boston Harbor
   hydrophone recordings. Laptop training is ~25 s/epoch at width 32; the GPU box lets us run width 64, 5 seeds,
   and the full 24-class set in the same wall-clock.
2. **Join NOAA ISD to the hydrophone noise floor.** NOAA's Integrated Surface Database (one of Voloridge's curated
   datasets, `s3://noaa-isd-pds`) gives hourly wind / pressure / precip at Boston Logan (`725090-14739`, 6 km from the
   buoy). We join it to the buoy's hourly noise floor and ask: how much of the underwater background is weather?
   That number is the "insight" slide.

```
public corpus (S3 / HF) ──┐                                 ┌── models/whale_cnn_volo.pt ──> pipeline/ (UNO Q)
                          ├── Voloridge GPU (g5, us-east-1) ─┤
Charles recordings ───────┘        train/pretrain.sh         └── models/whale_cnn_charles.pt
                                   train/finetune.py

s3://noaa-isd-pds ── data/fetch_isd.sh ── data/parse_isd.py ──┐
                                                              ├── analysis/join_isd.py ──> analysis/out/noise_vs_weather.*
pipeline/out/*.wav ── analysis/noise_floor.py ────────────────┘
```

## What Voloridge gives us

From their [challenge materials](https://voloridge-hack-mit-2026.s3.us-east-1.amazonaws.com/index.html):

- EC2 instances (CPU and GPU), **Amazon Linux 2023, `us-east-1`**, handed out at the booth after you pitch the project.
- The instances carry an `AmazonS3ReadOnlyAccess` role, so the public data buckets (`noaa-isd-pds`, etc.) read for free
  through the S3 gateway endpoint — same region, no egress.
- Per-dataset fetch tools: `aws s3 sync --no-sign-request s3://voloridge-hack-mit-2026/src ./vendor/voloridge`
  (`data/fetch_voloridge_tools.sh`). We use `noaa_isd/fetch.py` as-is instead of rolling our own.

Nothing here assumes anything else about the box: it is SSH + a GPU + Python, and everything runs inside a venv under
`~/keiko` on the instance.

## Layout

| Path | What |
|---|---|
| `voloridge.env.example` | copy to `voloridge.env`: instance host, SSH user/key. **Not committed.** |
| `Makefile` | every step below as a target |
| `configs/` | training hyperparameters for the GPU box, ISD station list |
| `infra/` | bootstrap the instance, rsync code up, pull models/runs down, run a command in a detached tmux session |
| `data/` | fetch Voloridge's tools, fetch + parse ISD, build features from the Charles recordings |
| `train/` | `pretrain.sh` (whale_cnn on the GPU), `finetune.py` (transfer to Charles classes) |
| `analysis/` | hourly noise floor from the recordings, join to ISD, correlations + plot |
| `vendor/` | Voloridge's `src/` tree (gitignored) |

## Run book

```bash
cd training/voloridge
cp voloridge.env.example voloridge.env      # fill in VOLO_HOST / VOLO_KEY from the booth
make check                                  # ssh works, nvidia-smi, disk
make bootstrap                              # one-time: dnf, venv, torch cu12, boto3, voloridge tools
make sync-up                                # code + feature tensors -> ~/keiko on the instance
make pretrain                               # detached tmux; make logs to follow
make finetune                               # after pretrain; needs data/charles features (make charles-features)
make sync-down                              # runs/ + models/ back to this folder
```

ISD + noise floor (runs anywhere; no GPU; `make all-local` does all of it):

```bash
make tools                                  # vendor/voloridge from their S3 bucket
make isd                                    # Logan 2024:2025 + station metadata -> data/noaa_isd/ (their fetch.py)
make isd-parse                              # fixed-width .gz -> data/isd_hourly.csv
make nws                                    # last 7 days of live KBOS obs, same schema, merged in (see below)
make noise-floor                            # pipeline/out/*.wav -> analysis/out/noise_floor_hourly.csv
make join                                   # -> analysis/out/noise_vs_weather.csv + .png + summary.json
```

Python: the Makefile uses `../../.venv/bin/python` (the repo venv `pipeline/Makefile` creates) if it exists, else
`python3`; override with `make PY=...`. Needs `boto3 matplotlib` on top of the pipeline's requirements.

## Training plan on the GPU box

| run | features | model | why |
|---|---|---|---|
| `volo_w64` | `v2_32k_mel128_3s` (71k windows, 22 classes) | width 64, 40 epochs, batch 256 | 4x the laptop model; the laptop can't hold it in RAM with the tensors |
| `volo_w64_s{1..4}` | same | 4 more seeds | seed variance on the dolphin genera, which sit at F1 0.0-0.2 on one seed |
| `volo_full24` | same, `--no_merge_rare` | width 64 | do the 4 rare species come back with capacity? |
| `charles_ft` | `data/charles_v2` | init from `volo_w64`, stem + blocks 0-1 frozen | our own water: motorboat / crew shell / ambient / rain / unknown |

Everything writes `runs/<name>/{best.pt,test_metrics.json,test_confusion.csv}` and exports to `models/`, same as
`../whale_cnn/train.py`, so `pipeline/keiko_pipeline.py --model` can take any of them unchanged.

## The ISD join

ISD records are fixed-width, one per observation; `data/parse_isd.py` pulls the mandatory section (wind dir/speed,
temperature, dew point, sea-level pressure, visibility) and the `AA1` precipitation group, drops rows with failing QC
codes, and resamples to the hour. `analysis/noise_floor.py` computes the 30th-percentile band level in 10-1000 Hz per
recording (the same statistic the live pipeline calls `floor`) and buckets it hourly in UTC. `analysis/join_isd.py`
inner-joins on the hour and reports Spearman correlation of noise floor vs wind speed, vs precip, vs pressure
tendency, plus a partial residual after removing the diurnal boat-traffic cycle. Output is one CSV, one PNG, one JSON.

Station: Boston Logan Intl, USAF 725090 / WBAN 14739, 42.361 N 71.010 W, ~6 km from the buoy site. Other candidates
are in `configs/stations.txt` with the lookup recipe.

**Archive lag (checked 2026-09-20).** The public ISD archive — both `s3://noaa-isd-pds` and NCEI's own
`global-hourly/access/` — ends at **2025-08-27** for Logan (and has no `data/2026/` prefix at all). ISD is the archive
of the ASOS/METAR reports that the NWS API serves live, so `data/fetch_nws.py` pulls `api.weather.gov/stations/KBOS/
observations` for the recording window, maps it onto the same hourly columns, and merges it into `data/isd_hourly.csv`
with a `source` column (`isd` / `nws`). Same instrument, same station id, hours old instead of a year. The archive
side is still what gives the seasonal baseline (Jan-Aug 2025: 9,156 obs -> 5,714 station-hours).

**Status.** Parser, NWS fetch, noise floor and join are tested on real data: 2,067 KBOS obs from the last week,
16 field clips (2.1 min) -> 2 buoy-hours. Two hours is not enough to correlate (`join_isd.py` refuses below 4);
the stats + plot were exercised on a synthetic floor over the real weather series. The insight needs hours of
recording, ideally spanning a wind change — leave the buoy in while the GPU trains.
