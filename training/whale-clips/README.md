# Whale clips, Kaggle-style

Every kept whale source reshaped into the layout of the Kaggle *Whale Detection Challenge*
(Cornell / Marinexplore 2013): a flat folder of fixed-length, mono, 16-bit clips and a
`train.csv` whose first two columns are `clip_name,label`. The Kaggle data itself is in it.

```sh
python3 build_whale_clips.py --db ~/Projects/marine-sounds-db --out ~/Projects/marine-sounds-db/whale-clips --csv-copy .
```

Audio is not in git (6.9 GB). `train.csv.gz` here is the full label table; `build_stats.md` has
every kept / dropped count.

## What is in it

222,999 clips, 2.0 s, 8 kHz, mono, 16-bit PCM WAV. 194,251 whale (label 1), 28,748 noise (label 0).

| source | clips | whale | what they are |
|---|---:|---:|---|
| kaggle | 30,000 | 7,027 | the Kaggle zip's `train/` as-is: right-whale upcalls vs noise, Massachusetts Bay, resampled 2 → 8 kHz |
| dclde | 102,153 | 96,378 | DCLDE 2027 killer whale (27,113, with ecotype) and humpback (69,265) call boxes; each clip is a 2 s window cut from the **original recording** around the call, plus 5,775 noise windows (abiotic boxes and windows that overlap no annotation) |
| aad | 76,901 | 76,901 | Antarctic blue (48,006), fin (27,263), minke (1,424) and humpback (208) calls from the IWC-SORP library |
| watkins | 13,945 | 13,945 | 36 cetacean species, up to 3 windows per cut, wild recordings only |

## Cleaning applied

- **Uniform format.** Everything resampled to 8 kHz (the Keiko buoy's hydrophone rate; `--sr 2000`
  reproduces Kaggle exactly), mixed to mono, cut to 2.0 s. Source rates ranged 250 Hz – 256 kHz.
- **Real context, not padding.** DCLDE call boxes average 1.0 s, so the 2 s window is cut from
  the original 5-minute recording centred on the call, the way the Kaggle clips were made.
  Watkins cuts shorter than 2 s are centre-padded and `pad_s` says by how much.
- **Level.** Clips are peak-normalised to 0.9 full scale because several sources sit at
  ±10 LSB in 16-bit. `gain_db` is the gain applied, so relative loudness can be undone.
- **Dropped.** Synthetic Keiko rows; captive Watkins recordings; seals and sea otter; DCLDE
  "undetermined biological" boxes and killer-whale boxes the annotator flagged uncertain;
  Antarctic "unidentified call" tables; 12 windows from four UAF field WAVs that are not valid
  RIFF files (listed in `build_stats.md`).
- **Split.** `split` is a deterministic 85 / 15 train / test cut grouped by source recording,
  so no recording appears on both sides.

## Columns of train.csv

| column | meaning |
|---|---|
| `clip_name`, `label` | Kaggle header: file name, 1 = whale call, 0 = noise |
| `species`, `common_name`, `taxon_group`, `ecotype`, `call_type` | for multi-class targets; blank on noise |
| `datetime_utc`, `time_precision` | `second` (dclde, aad), `day` (watkins), `none` (kaggle) |
| `lat`, `lon`, `coord_precision_km`, `site_id`, `location_name` | sensor position where published; blank for Kaggle and the two DFO sites |
| `source`, `source_clip` | provenance, traceable back to the catalogue / annotation row |
| `orig_sr`, `pad_s`, `gain_db` | source sample rate, zero padding added, normalisation gain |
| `split` | `train` or `test` |

Two things to keep in mind when training: the noise class comes almost entirely from
Massachusetts Bay (Kaggle) and the NE Pacific (DCLDE), so a binary detector can learn "site"
instead of "whale" unless you balance by site; and the Kaggle clips carry no time or
position, so they are in this bundle but not in `../location/whale_locations.csv`.

## Tensors

`make_tensors.py` turns the bundle into a log-mel tensor for training; see its docstring.
