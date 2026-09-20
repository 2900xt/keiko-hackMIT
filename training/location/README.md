# Whale location table

A cleaned, model-ready table of **real** whale detections with a known sensor position and a
timestamp, built from the sources indexed in `training/dataset`. The committed catalog
(`catalog/clips.csv.gz`) carries only free-text location strings and recordist notes, so the
script reads the raw downloads that `training/dataset/fetch_data.sh` produces (Watkins parquet
shards, the DCLDE `Annotations.csv`, the AAD Raven selection tables). Rebuild with:

```sh
python3 build_whale_locations.py --db ~/Projects/marine-sounds-db
```

## What was triaged

`open-source/data/` (the Keiko detection database) was the first candidate and is **not used**:
all 24 rows carry `source = synthetic`, the generator (`tools/keiko_data.py synth`) draws each
position uniformly within 450 m of a buoy in the Charles River, and the audio is a noise floor
plus a sine sweep. There is no whale signal in it. Field rows (`source = field`) can be appended
to this table once the buoys record real detections.

| source | verdict | why |
|---|---|---|
| Keiko `open-source/data` | dropped | 100 % synthetic, random positions in a river |
| Watkins (WHOI) | **kept**, 11,225 cuts, 214 recording-day events | species + date + position per recording, 1951–1999, worldwide |
| DCLDE 2027 killer whale | **kept**, 34,423 calls, 5,537 minute events | per-call UTC at 23 fixed hydrophones in WA / BC / AK; ecotype labels |
| AAD / IWC-SORP Antarctic blue & fin | **kept**, 77,080 calls, 42,777 minute events | per-call UTC at 10 Antarctic moorings, 2005–2017 |
| DCLDE DFO sites (WVanIsl, NorthBc, WDLP) | dropped, 148,820 calls | hydrophone positions unpublished (paper says so) |
| Watkins captive recordings | dropped, 1,595 cuts | aquarium / tank / zoo, no wild position |
| Watkins seals, sea otter, undated, unpositioned | dropped, 2,428 cuts | not a cetacean, or nothing to place on a map |
| Cornell right-whale challenge | dropped | no per-clip date or position |
| BEANS HICEAS minke | dropped | towed array on a moving ship, no track in the data |
| Orcasound Pod.Cast | dropped | duplicate of the DCLDE `orcasound_lab` annotations |
| ReefSet, ToadFishFinder, Zenodo fish | dropped | not whales |
| "Unidentified call" tables (AAD, DCLDE UndBio / AB) | dropped | no species |

Full step-by-step counts are in `build_report.md`.

## Cleaning applied

- **Positions.** Watkins stores whole-degree coordinates (±60 km). 2,309 cuts have a finer
  position in the recordist's note in six different notations (`N42 14'`, `N39' 45`, `N32'21`,
  `N15 13.92`, `S77.48`, `W156`); these are parsed, cross-checked against the record position
  (must agree within 2°), and used with `coord_precision_km = 2`. DCLDE positions come from the
  deployment table in Palmer et al. 2025 (Sci Data, PMC12229703); AAD positions from the library's
  own `folderStructure.csv`. `coord_precision_km` and `coord_source` say which.
- **Times.** Four date formats normalised to ISO-8601 UTC. Watkins is day-resolution
  (`time_precision = day`); the others are floored to the minute.
- **Species.** Scientific + common name from the catalogue; DCLDE `KW` → *Orcinus orca* with
  ecotype (SRKW / NRKW / TKW / SAR / OKW), `HW` → humpback; AAD file names → Antarctic blue or fin
  whale + call type. Killer-whale calls the annotator flagged uncertain (`KW_certain = 0`) are dropped.
- **Duplicates.** Watkins cuts from the same tape collapse to one row per species × day ×
  position; DCLDE / AAD calls collapse to one row per site × species × minute. `n_detections`
  keeps the count.

## Files

`whale_locations.csv` — one row per detection event.

| column | meaning |
|---|---|
| `source` | `watkins`, `dclde`, `aad` |
| `site_id`, `location_name` | sensor / recording site (registry in `sites.csv`) |
| `lat`, `lon` | sensor position, decimal degrees WGS84 |
| `coord_precision_km`, `coord_source` | positional uncertainty and where the position came from |
| `datetime_utc`, `time_precision` | ISO-8601 UTC; `day` or `minute` |
| `species`, `common_name`, `taxon_group` | scientific name, common name, baleen / toothed whale |
| `ecotype` | killer-whale ecotype (DCLDE only) |
| `call_type` | call class where the source gives one |
| `n_detections` | calls / cuts collapsed into this row |
| `source_ref` | record numbers or annotation file, for tracing back |

`whale_presence_daily.csv` — site × species × date with detection counts (2,205 rows), the
natural table for a seasonal presence model. `sites.csv` — 170 sensor sites.

```python
import pandas as pd
ev = pd.read_csv("whale_locations.csv", parse_dates=["datetime_utc"])
daily = pd.read_csv("whale_presence_daily.csv", parse_dates=["date"])
```

## What this can and cannot train

- The position is the **sensor's**, not the whale's. Watkins recordings were made from a vessel
  next to the animals, so the two nearly coincide. Fixed hydrophones hear killer whales within
  roughly 5–10 km and blue / fin whales within tens to a few hundred km.
- It is **presence-only**. Nothing here records listening effort or silence, so absence labels
  have to be constructed (e.g. sample site-hours inside each deployment window with no
  detection). Deployment windows per site are the `first` / `last` columns in `build_report.md`.
- It supports a species × place × season occupancy model (where and when each species is heard)
  and per-site time-series models of daily detection rate. It does not support fine-scale
  trajectory tracking: no row is a whale moving between positions. For that, the next data to add
  is a tagging / sighting track source (Movebank, OBIS-SEAMAP, NOAA right-whale sightings) or
  multi-buoy time-difference-of-arrival from the Keiko buoys once more than one is in the water.
