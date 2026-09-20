# Keiko pipeline (MVP)

Turns a hydrophone node's UDP stream into whale detections on the website, in one process:

```
node UDP (KEIK packets) ─► 3 s windows, 50% overlap ─► whale CNN v2 ─► event (run of whale windows)
                                                                          ├─► out/<id>.wav + out/events.jsonl
                                                                          └─► --archive: open-source/data via keiko_data.py add
```

| | |
|---|---|
| `keiko_pipeline.py` | the receiver + classifier + event logic (`--wav` runs it over a file instead of the network) |
| `replay_wav.py` | streams any WAV as node packets, for demos and tests without a board |
| `requirements.txt` | torch, librosa, soundfile … (same as `training/whale_cnn`, plus scipy/matplotlib/pillow for `--archive`) |

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install -r pipeline/requirements.txt      # once, from the repo root
```

Live, on a laptop on the same network as the UNO Q — set `KEIKO_UDP_HOST` in `firmware/unoq/python/keiko.env`
to the laptop's IP, `make start` there, then:

```bash
.venv/bin/python pipeline/keiko_pipeline.py
```

Offline, over a recording (`make record` in `firmware/unoq` makes one):

```bash
.venv/bin/python pipeline/keiko_pipeline.py --wav firmware/unoq/recordings/<utc>.wav
```

Demo without a board — two terminals:

```bash
.venv/bin/python pipeline/keiko_pipeline.py --min_conf 0.5
.venv/bin/python pipeline/replay_wav.py some_whale_call.wav --loop
```

One line per window (`WHALE` marks windows that pass the abstain rule), then `EVENT …` when a run of whale windows
ends. Add `--archive` to write each event into `open-source/data/` (clip, spectrogram, CSV + JSON row); commit that
folder and the site shows it. Events land in `pipeline/out/` regardless (gitignored).

## Knobs

- `--min_conf 0.8 --margin 0.2` — `predict.py`'s abstain rule. The v2 model calls 25–36 % of non-whale windows a
  whale at its defaults (0.5 / 0.1), and on the UNO Q's floating input it said "sperm whale 0.56", so the pipeline
  defaults are stricter. Lower them for a demo with real calls.
- `--min_windows 2` consecutive whale windows to open an event, `--patience 2` no-whale windows to close it,
  `--max_s 30` hard cap. Clip = event ± 0.5 s at the node's own sample rate.
- `--buoy KEIKO-01` looks up position in `open-source/data/buoys.csv`; `--lat/--lon` override.
- `--hop 1.5` seconds between classifications (~15 ms of CPU per window on an M-series Mac; the model is small).

## Caveats

- The UNO Q node samples at 3.3 kHz (Nyquist 1.67 kHz). The model was trained on 32 kHz audio with bandwidth masking,
  so low-frequency species (right, fin, minke, blue, bowhead) are in band; dolphins and clicks are not.
- Species names shown on the site are common names mapped from the model's classes (`COMMON` in the script);
  dolphin genera are lumped by the model itself.
- Not yet: running on the board (no torch there — the ONNX model + onnxruntime would fit), Elasticsearch ingest,
  the site's Live tab (spectrogram/level feed).
