# Marine Animal Sound Database

One unified, ML-ready database of ocean animal sounds matched to the animal that made them, plus a
literature-derived catalog of every public marine bioacoustics dataset found in a sweep of 2015–2026 papers.

Built 2026-09-19. **The audio is not in git.** Run `./fetch_data.sh` (needs `aria2c`, `unzip`, `python3` with
`huggingface_hub pyarrow soundfile numpy`) to download the raw sources and rebuild `audio/` exactly as indexed in
`marine_sounds.sqlite` / `catalog/clips.csv` (paths are relative to this folder). Everything else lives here.

## What's here

| Path | What it is |
|---|---|
| `marine_sounds.sqlite` | The database. Tables: `species`, `sound_types`, `datasets`, `clips`; views `v_clips`, `v_species_summary`. |
| `audio/<dataset>/<taxon or label>/*.wav` | 126,563 extracted clips (16 GB). Every file has a row in `clips`. |
| `catalog/clips.csv`, `species.csv`, `sound_types.csv`, `datasets.csv` | Flat exports of the DB. |
| `catalog/survey_*.md` | The three literature-sweep reports (marine mammals; fish & invertebrates; download endpoints). |
| `catalog/datasets_*.csv`, `species_sounds_*.csv` | The survey tables as CSV. |
| `scripts/build_db.py` | Rebuilds `marine_sounds.sqlite` + `audio/` from `raw/`. Idempotent. |
| `scripts/download_watkins.py`, `md_tables_to_csv.py` | Helpers. |
| `raw/` | Original downloads (parquet shards, zips, tarballs). Safe to delete once `audio/` exists (~20 GB). |

## Audio in the database

| Source | Clips | Hours | Taxa | Labels | License |
|---|---|---|---|---|---|
| Watkins Marine Mammal Sound Database, all cuts (WHOI; HF mirror `ivangtorre/watkins-marine-mammal-full-cuts`) | 15,248 | 28.2 | 52 marine mammal species (baleen & toothed whales, dolphins, porpoises, 14 seals/sea lions/walrus, sea otter) | species (via Watkins code) + call-type keywords mined from the recordist notes; date, location, lat/lon, sample rate 600 Hz–192 kHz | free for personal/academic (non-commercial) use |
| ReefSet v1.0 (UCL / Google SurfPerch; Zenodo 11071202) | 57,074 | 30.4 | reef biophony, 16 datasets, 12 countries: humpback, plainfin midshipman, black grouper, red hind, Ambon damselfish, squirrelfish, damselfish, dolphins, sea urchins, snapping shrimp, 20 unidentified fish call types, plus ambient/boat/waves negatives | 37 classes, 1.88 s @ 16 kHz | CC BY 4.0 |
| ToadFishFinder v4 (NC State; Zenodo 8225808) | 20,914 | 7.8 | oyster toadfish *Opsanus tau* boatwhistles (10,018) vs other sounds (10,896) | binary, 1.35 s @ 24 kHz, Pamlico Sound NC | CC0 |
| Cornell/Marinexplore Whale Detection Challenge (Kaggle 2013), full training set via HF `monster-monash/CornellWhaleChallenge` | 30,000 | 16.7 | North Atlantic right whale *Eubalaena glacialis* upcalls (7,027) vs noise (22,973), Cornell MARU buoys, Massachusetts Bay | binary, 2 s @ 2 kHz; MONSTER 5-fold CV index in `note` | Copyright Cornell (Kaggle competition rules, research) |
| BEANS `hiceas` minke boing set (HICEAS 2017 towed array, NOAA PIFSC) | 1,329 | 11.8 | minke whale *Balaenoptera acutorostrata* boings (680, cut to call) vs 1-min negatives (533) | time-stamped boings @ 22.05 kHz | NOAA public domain |
| Orcasound Pod.Cast rounds 2, 3 + test (S3 `acoustic-sandbox`) | 887 | 0.5 | Southern Resident killer whales, Orcasound Lab hydrophone 2017/2019 | each labeled call cut to its own clip @ 20 kHz | CC BY-NC-SA 4.0 |
| Marine sounds < 2 kHz, French Polynesia (Zenodo 12570714) | 1,222 | 3.7 | unidentified reef fish (mainly), 80+ sound-type codes from the published identification key | folder = sound type | CC BY 4.0 |
| Southern Ocean fishes, Prince Edward Islands (Zenodo 17076825) | 3 | – | unidentified benthic fish: drum, grunt series, pops | | CC BY 4.0 |
| Bluefin gurnard *Chelidonichthys kumu* (Zenodo 4972259) | 2 | – | growl, grunt | | CC0 |

Totals: **126,563 clips, ~99 hours, 59 species with audio** (30 toothed whales, 8 baleen whales, 14 pinnipeds,
6 fish, 1 sea otter) plus family-level and unidentified classes. Species with the most audio: oyster toadfish
(10k), North Atlantic right whale (7.5k), plainfin midshipman (4.7k), killer whale (3.5k), humpback (3.1k), sperm whale (1.3k, 11.7 h).

## Knowledge layer (no audio, from the literature sweep)

- `sound_types`: 122 species/call-type rows (e.g. NARW upcall 50–200 Hz ~1 s; harbour porpoise NBHF click ~130 kHz;
  snapping shrimp snap 2–200 kHz; fin whale 20 Hz pulse) with frequency range, duration, which datasets contain it,
  and the paper/page it came from.
- `datasets`: 75 datasets from the papers (DCLDE 2013–2027, NOAA NEFSC/PIFSC/SanctSound, Antarctic blue/fin
  library, DOCC10, FishSounds.net, Australian fish chorus catalogue, etc.) with host, URL, size, sample rate,
  label format, license and the papers that used them. `downloaded=1` marks the nine with audio here.
- `catalog/survey_registries_endpoints.md`: verified bulk-download mechanics (GCS `noaa-passive-bioacoustic`
  bucket layout, Orcasound S3 keys, ONC API, MBARI AWS, Watkins URL patterns via Wayback). Note: WHOI's Watkins
  site was down for maintenance on 2026-09-19 and the Kaggle mirror is a 404; the HF mirrors are the fallback.

## Using it

```python
import sqlite3, pandas as pd
con = sqlite3.connect("marine_sounds.sqlite")
df = pd.read_sql("SELECT * FROM v_clips WHERE scientific_name IS NOT NULL", con)   # species-labeled clips
df.groupby("scientific_name").size().sort_values()
```

```sql
-- what does a killer whale sound like, and where is the audio?
SELECT sound_type, freq_range_hz, duration FROM sound_types t JOIN species s USING(species_id) WHERE s.scientific_name='Orcinus orca';
SELECT file_path, sound_type, location FROM v_clips WHERE scientific_name='Orcinus orca' LIMIT 5;
```

Caveats for training:
- Watkins sample rates are heterogeneous (600 Hz–192 kHz); resample. Many recordings are 1950s–1990s analog tape.
- Watkins `sound_type` is keyword-mined from free text ("Squeals; clicks" → `squeal;click`), not expert call-type annotation.
- Right whale clips are 2 kHz, 2 s, int16. Class imbalance elsewhere is severe. Toadfish and midshipman dominate fish; common dolphin and false killer whale dominate Watkins.
- ReefSet species-level labels (`bioph_megnov` etc.) were resolved from the SurfPerch paper's label key; the
  20 "unidentified reef fish" call types are labeled by sound, not species.
- Licenses differ per source (see `clips.license`). Watkins and Orcasound are non-commercial.

## ML features (whales)

`scripts/extract_whale_features.py` turns every whale clip into fixed-size log-mel spectrogram tensors:

```bash
python3 scripts/extract_whale_features.py        # ~1 min on 8 cores; needs librosa, soundfile, numpy; audio/ must exist
```

Output in `features/whales_32k_mel128_3s/`:
- `windows.npy` — float16, shape (47,253, 128, 301): 3 s windows @ 32 kHz, 128 mel bins (10 Hz–16 kHz), n_fft 1024, hop 320,
  log1p + per-window z-score. Short clips are centered and zero-padded; long clips are cut with 50% overlap, capped at 30 windows.
  **Not in git (3.4 GB)** — regenerate with the command above.
- `manifest.csv` (in git) — one row per window: clip_id, species, label, label_id, recording group, source, location, date,
  **split**, offset. 24 classes = 23 species with ≥100 clips + `other_whale`.
- `labels.json` (in git) — label→id, config, per-class counts per split.

The split is by recording *group* (Watkins tape, Kaggle fold, Orcasound date, ReefSet site), stratified per class,
so no session leaks between train/val/test (30,232 / 9,233 / 7,788 windows). Four species have too few tapes to split
fairly (melon-headed whale, Clymene dolphin, Atlantic spotted dolphin, Fraser's dolphin); fold them into `other_whale`
with `--min_clips 250` or don't evaluate on them. Use a weighted sampler and macro-F1.

```python
import numpy as np, pandas as pd
X = np.load("features/whales_32k_mel128_3s/windows.npy", mmap_mode="r")
m = pd.read_csv("features/whales_32k_mel128_3s/manifest.csv")
tr = m.index[m.split == "train"].values
x, y = X[tr[:256]].astype("float32")[:, None], m.label_id.values[tr[:256]]   # (256, 1, 128, 301)
```

### v2 features (whales + NOT-a-whale classes) — `features/v2_32k_mel128_3s/`

```bash
python3 scripts/extract_features_v2.py     # ~90 s; 71,522 windows, 22 classes, 5.1 GB windows.npy (not in git)
```
Same tensor format as above, but: labels are species for baleen + non-dolphin toothed whales, **genus** for dolphins,
`other_baleen`/`other_toothed`, plus `no_whale_noise` and `no_whale_biophony`; a class needs ≥100 clips and ≥4 recording
groups; each class is capped at 6,000 windows drawn evenly across recording groups; z-scoring is per recording (whole clip)
rather than per window. `manifest.csv` has a `hierarchy` column (baleen / toothed / no_whale) and keeps the orca ecotype in
`taxon_label`. This is what `../whale_cnn/models/whale_cnn_v2.pt` was trained on.

## Rebuild / extend

```bash
python3 scripts/build_db.py          # re-extracts audio (skips existing files) and rebuilds the sqlite
```
To add a source: drop it under `raw/`, add a `load_<name>()` method following the existing ones, register in `__main__`.
Good next additions (all open, endpoints in `catalog/survey_registries_endpoints.md`): DCLDE 2027 killer-whale
ecotype set (225k boxes, 1.6 TB), Antarctic blue/fin library (105k annotations), BEANS `hiceas` minke boings (1.4 GB), 
ANIMAL-SPOT tarball (547 MB), NOAA NEFSC right-whale upcall logs, Belize manatee calls.
