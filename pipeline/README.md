# Keiko pipeline (MVP)

Turns a hydrophone node's UDP stream into whale detections on the website, in one process:

```
node UDP (KEIK packets) ─► 3 s windows, 50% overlap ─► whale CNN v2 ─► event (run of whale windows)
                                                                          ├─► out/<id>.wav + out/events.jsonl
                                                                          └─► --archive: site/data via keiko_data.py add
```

| | |
|---|---|
| `keiko_pipeline.py` | the receiver + classifier + event logic (`--wav` runs it over a file instead of the network) |
| `replay_wav.py` | streams any WAV as node packets, for demos and tests without a board |
| `requirements.txt` | torch, librosa, soundfile … (same as `training/whale_cnn`, plus scipy/matplotlib/pillow for `--archive`) |
| `Makefile`, `live.sh`, `demo.sh`, `netinfo.py`, `usb_relay.py` | `make test` / `make demo` / `make live` (see below) |
| `test_pipeline.py` | offline regression: noise → no events, humpback sample → humpback event |
| `samples/humpback_nps.mp3` | 38 s of humpback song, National Park Service, public domain — the demo and test input |

## Setup

```bash
cd pipeline && make venv          # once: ../.venv with torch, librosa, ... (a few minutes)
```

## Test (no hardware)

```bash
make test
```

Runs the pipeline over 20 s of white noise at the UNO Q's 3333 Hz (must give no events) and over
`samples/humpback_nps.mp3` (must give a humpback event). Takes ~15 s. Run it after touching thresholds or the model.

## Demo (no hardware)

```bash
make demo                         # ctrl-c stops it
```

`demo.sh` loops the humpback sample through `replay_wav.py` as if a node were streaming it, and runs the pipeline on
it with `--min_conf 0.6`. Expect a `WHALE Megaptera_novaeangliae` line every 1.5 s during song and an `EVENT …
humpback whale` line when each bout ends. `make demo ARGS="--archive --source synthetic"` also writes the events into
`site/data/` so the website's Database tab shows them (revert or commit that folder afterwards).

The sample is a National Park Service recording from the Glacier Bay hydrophone (public domain, via
[archive.org](https://archive.org/details/HumpbackWhalesSongsSoundsVocalizations)). Any WAV/FLAC/MP3 works:
`CLIP=path make demo`.

## Live against the UNO Q

Board plugged into this machine over USB-C (control goes over adb), board and machine on the same Wi-Fi (the audio
comes over UDP). Venue Wi-Fi usually will not do — MIT GUEST puts the board behind a captive portal and isolates
clients — so use a phone hotspot: join this machine to it, then join the board with

```bash
make -C ../firmware/unoq wifi SSID='<hotspot name>' PSK='<password>'
make live                         # add ARGS="--archive" to write detections to the site database
```

`live.sh` does what you would do by hand:

1. `netinfo.py` asks the board for its addresses over adb and picks this machine's IP on the same subnet
   (override with `UDP_HOST=<ip> make live`).
2. `make -C ../firmware/unoq retarget UDP_HOST=<ip>` pushes a `keiko.env` with that address. The node re-reads the
   file every second and switches its UDP destination — no app restart (restarts re-flash the MCU and have wedged
   the board's router).
3. If the app is not running it runs `make start` there (first time: ~2 min).
4. Prints the node's health line and starts the pipeline. Within a couple of seconds you should see
   `receiving from 192.168.x.y` (or whatever the hotspot hands out), then one line per 1.5 s.

If the pipeline prints `no packets for N s`: check `make -C ../firmware/unoq logs` shows `fs=…` lines (if it stops at
"App started", power-cycle the board), and that both machines really share a network (`netinfo.py` warns when they do
not; `make -C ../firmware/unoq ip` shows the board's). `make -C ../firmware/unoq retarget UDP_HOST=auto` sends the
stream back to the board itself.

No usable network at all? `VIA=usb make live` carries the stream over the USB cable instead: adb cannot forward
UDP, so `usb_relay.py node` on the board wraps each datagram in a length prefix and sends it down
`adb reverse tcp:5006`, and `usb_relay.py host` here unwraps it onto UDP 127.0.0.1:5005 (you then see
`receiving from 127.0.0.1`). ~7 kB/s, no drops; Ctrl-C removes the relay again.

Offline over a recording (`make record` in `firmware/unoq` makes one):

```bash
../.venv/bin/python keiko_pipeline.py --wav ../firmware/unoq/recordings/<utc>.wav
```

What the output means: one line per window (`WHALE` marks windows that pass the abstain rule), then `EVENT …` when a
run of whale windows ends. Events always land in `pipeline/out/` (gitignored) as a clip WAV plus a line in
`events.jsonl`; with `--archive` they also go through `site/tools/keiko_data.py add` (clip, spectrogram,
CSV + JSON row) — commit that folder and the site shows them.

## Knobs

- `--min_conf 0.8 --margin 0.2` — `predict.py`'s abstain rule. The v2 model calls 25–36 % of non-whale windows a
  whale at its defaults (0.5 / 0.1), and on the UNO Q's floating input it said "sperm whale 0.56", so the pipeline
  defaults are stricter. Lower them for a demo with real calls.
- `--min_windows 2` consecutive whale windows to open an event, `--patience 2` no-whale windows to close it,
  `--max_s 30` hard cap. Clip = event ± 0.5 s at the node's own sample rate.
- `--buoy KEIKO-01` looks up position in `site/data/buoys.csv`; `--lat/--lon` override.
- `--hop 1.5` seconds between classifications (~15 ms of CPU per window on an M-series Mac; the model is small).

## Caveats

- The UNO Q node samples at 3.3 kHz (Nyquist 1.67 kHz). The model was trained on 32 kHz audio with bandwidth masking,
  so low-frequency species (right, fin, minke, blue, bowhead) are in band; dolphins and clicks are not.
- Species names shown on the site are common names mapped from the model's classes (`COMMON` in the script);
  dolphin genera are lumped by the model itself.
- `--elastic` ships every window and event to Elasticsearch (embeddings, spectral descriptors, packet loss);
  see `elastic/README.md` for setup, the dashboard, kNN/ELSER search and the ES|QL agent.
- Not yet: running on the board (no torch there — the ONNX model + onnxruntime would fit).
