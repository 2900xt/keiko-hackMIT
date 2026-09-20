# Keiko — HackMIT 2026

Hydrophones in Boston Harbor that turn underwater sound into a live, searchable stream of what's happening on the
water: whale species, where they are, how the soundscape is drifting, and an alert when a right whale is heard.
Built by [Moby Labs](https://github.com/2900xt) at HackMIT 2026.

**Live site:** <https://2900xt.github.io/keiko-hackMIT/> · **Team:** Taha Rawjani ([@2900xt](https://github.com/2900xt)) · Matthew Li ([@Mallhw](https://github.com/Mallhw))

```
                        ┌─ Arduino UNO Q  (STM32U585 MCU → Bridge → Linux/Python)  3.3 kHz, 14-bit ─┐
 piezo hydrophones ──── ├─ ESP32-S3 DevKitC-1 (hw-timer ISR → USB-CDC or Wi-Fi)    8 kHz,   12-bit ─┼─ UDP "KEIK" datagrams :5005
                        └─ nRF7002 DK (nRF5340 SAADC → nRF70 Wi-Fi)                8.2 kHz, 12-bit ─┘
                                                                                                     │
        ┌────────────────────────────────────────────────────────────────────────────────────────────┘
        ▼
 pipeline/keiko_pipeline.py     3 s windows @ 1.5 s hop ─► whale CNN v2 (22 classes) ─► abstain rule ─► event = run of whale windows
        │                                                                                        │
        ├─► pipeline/out/<id>.wav + events.jsonl                (always)                          │
        ├─► site/data/  clip + spectrogram + CSV/JSON row       (--archive)  ─► GitHub Pages      │
        ├─► server/keiko_server.py  TDOA fix + tracks ─► WebSocket ─► site Live tab   (--server)  │
        └─► Elasticsearch  keiko-windows / keiko-detections     (--elastic)                       │
                 │  geo_point · 512-d dense_vector (cosine) · semantic_text (ELSER) · ML anomaly job
                 └─► Kibana dashboard · ES|QL alert rule → Discord/Slack · ask.py (Claude ⇄ ES|QL / kNN / ELSER)

 training/   dataset (126k clips, 9 sources) ─► whale CNN v2 (laptop) ─► Voloridge AWS GPU (width 64, 5 seeds, Charles fine-tune)
             NOAA ISD (s3://noaa-isd-pds, Voloridge) ⋈ buoy noise floor ─► "how much of the underwater background is weather?"
```

## Table of contents

- [How it works](#how-it-works)
- [Sponsor integrations](#sponsor-integrations) — Arduino · Espressif · Nordic/Hackster · Elastic · Voloridge
- [Wire protocols](#wire-protocols)
- [Models](#models)
- [Repository layout](#repository-layout)
- [How to run](#how-to-run)
- [Tests](#tests)

## How it works

1. **Capture.** A piezo-disc hydrophone (three 27 mm discs in parallel, potted in epoxy — `hardware/hydrophone-cup/`) feeds
   an analog front end into a microcontroller ADC. Three node designs exist (UNO Q, ESP32-S3, nRF7002 DK); each samples in a
   timer-paced thread into 256-sample blocks and ships them as identical `KEIK` UDP datagrams, so the pipeline does not care
   which board is on the other end. Node id, sample rate and timestamps travel in the header.
2. **Classify.** `pipeline/keiko_pipeline.py` reassembles the stream per node, resamples to 32 kHz, cuts 3 s log-mel windows
   (128 mel, 10 Hz–16 kHz, n_fft 1024, hop 320) every 1.5 s and runs the whale CNN v2 (~1.2 M params, ~15 ms/window on an
   M-series CPU). An abstain rule (`P(any whale) − P(no_whale) > margin` **and** top whale class `≥ min_conf`) turns the 22-way
   softmax into whale / no-whale; ≥ 2 consecutive whale windows open an *event*, 2 no-whale windows close it, 30 s hard cap.
3. **Fan out.** Every event lands in `pipeline/out/` as a WAV clip + JSONL line. Flags add sinks: `--archive` writes the
   detection database the website reads, `--server` streams telemetry/audio/windows/events to the central server (TDOA
   localization + tracks + WebSocket to browsers), `--elastic` indexes every window and event into Elasticsearch.
4. **Ask.** Kibana dashboards, an ES|QL alert rule, kNN "sounds like" over the CNN embedding, ELSER semantic search over
   generated descriptions, an ML anomaly job on the soundscape, and `ask.py` — a Claude agent that writes and runs ES|QL.

## Sponsor integrations

<details>
<summary><b>Arduino — UNO Q</b> (Touch Grass) · <code>firmware/unoq/</code></summary>

The UNO Q is the node we actually ran in the water. It is two computers on one board and we use both:

- **MCU side (STM32U585, Zephyr via `arduino:zephyr:unoq`).** `sketch/hydro.cpp` runs a cooperative thread paced by a kernel
  timer, reads `A0` with the 14-bit ADC at 3333 Hz (`SAMPLE_PERIOD_US` must be a multiple of the 100 µs Zephyr tick), fills
  a ring of 256-sample blocks, and pushes each block over **Bridge** with `Bridge.notify("hydro/block", …)`. The `.ino` is an
  empty stub so the prototype generator never touches the code.
- **Linux side (Python in an App Lab container).** `python/main.py` receives the notifications, measures the true sample
  rate from MCU timestamps, prints a health line once a second (`fs= 3333.3Hz blocks/s= 13 dc=1.71V rms= 4.2mV …
  mcu_drops=0 missing=0`), forwards every block as a `KEIK` datagram to `KEIKO_UDP_HOST:5005`, and optionally appends a WAV.
  Outside App Lab it speaks MessagePack-RPC to `/var/run/arduino-router.sock` directly.
- **Configuration without restarts.** App Lab's `app.yaml` has no env section, so settings live in `python/keiko.env`; the
  node re-reads it every second, so `make retarget UDP_HOST=<ip>` redirects the stream with no restart (restarts re-flash the
  MCU over SWD and have wedged the board's router — see the pipeline README).
- **Analog front end (3.3 V, not 5 V tolerant).** Two PN2222 as a Darlington emitter follower, ~1 MΩ input impedance, mid-rail
  bias, output idling at ~1.7 V (`dc=` on the health line must read 1.5–1.9 V or the follower is miswired).
- **Deployment over USB (adb).** A fresh board has SSH off; `make start` rsyncs the app to `~/ArduinoApps/keiko-unoq` over
  `adb push` and runs `arduino-app-cli app restart`, which compiles the sketch *on the board*, flashes the MCU, and starts
  the container. `make wifi SSID=… PSK=…` joins a hotspot over USB (`nmcli`). `VIA=ssh` switches every target to SSH.
- **USB fallback for the audio.** Venue Wi-Fi isolates clients, and adb cannot forward UDP, so `pipeline/usb_relay.py`
  wraps each datagram in a length prefix on the board, sends it down `adb reverse tcp:5006`, and unwraps it onto UDP on the
  laptop (`VIA=usb make live`). ~7 kB/s, no drops.
- **Limit.** The Bridge UART runs at 115200 baud (~11 kB/s), which caps 16-bit audio at ~3.3 kHz (Nyquist 1.67 kHz): fine for
  baleen whales and boats, not dolphin clicks — hence the two wideband nodes below.

</details>

<details>
<summary><b>Espressif — ESP32-S3-DevKitC-1 (N8R8)</b> (Best Use of Espressif Hardware) · <code>firmware/esp32-s3/</code></summary>

The wideband, laptop-optional node. Same analog front end as the UNO Q, on **GPIO1 = ADC1_CH0** (ADC2 is shared with the
Wi-Fi radio and returns garbage while it is on).

- **Sampler.** A 1 MHz hardware timer ISR wakes a FreeRTOS task that `analogRead`s at 8 kHz (12-bit, 11 dB attenuation →
  0–3.1 V) into a ring of 256-sample blocks. `analogRead` costs ~25 µs, so the period can drop to ~50 µs (20 kHz) before
  ticks are missed.
- **Two transports, selected at compile time.**
  - *USB mode:* frames go out over the **native USB-Serial-JTAG** port (~1 MB/s, so no UART bottleneck) as `KBLK` frames with a
    CRC-16/CCITT-FALSE, resynchronised on the magic if a byte is lost. `python/main.py` on the laptop validates the CRC,
    re-emits each frame as a `KEIK` datagram, and prints the health line (adds `crc_bad=`).
  - *Wi-Fi mode:* copy `sketch/wifi_config.h.example` → `wifi_config.h` (gitignored) with SSID/PSK/pipeline address and
    reflash. The board then builds the `KEIK` datagram itself (`fs` measured on-board, `t_ns` = `esp_timer_get_time()` × 1000)
    and sends it straight to the pipeline. Serial frames still flow when a host is attached; unplugged, the sender skips
    serial so a stalled USB write can never block the Wi-Fi path.
- **Build.** `sketch.yaml` profile `esp32:esp32:esp32s3` with native USB CDC, 8 MB flash, octal PSRAM; `make flash`
  auto-detects `/dev/cu.usbmodem*`. First flash over native USB may need BOOT-held + RESET.
- **Buoy.** `hardware/buoy-v2/` is a parametric OpenSCAD hull sized for exactly this DevKitC plus a 5,000 mAh bank, antenna
  ~31 mm above the waterline, reviewed adversarially by OpenAI Codex (`codex_*.md`).

</details>

<details>
<summary><b>Nordic Semiconductor — nRF7002 DK</b> (Hackster "Create What's Next") · <code>firmware/nrf7002/</code></summary>

A port of the UNO Q sampler to the nRF5340 app core with **no Linux side at all**: the MCU owns the Wi-Fi link.

- **Stack.** Zephyr / nRF Connect SDK v3.0 (`nrf7002dk/nrf5340/cpuapp`, `CONFIG_WIFI_NRF70`), IPv4 + DHCP + UDP sockets,
  `CONFIG_DNS_RESOLVER` so the UDP target can be a hostname. `src/main.c` has the same kernel-timer-paced sampler thread and
  ring as the UNO Q, then a sender loop on `main` and a health line on the J-Link VCOM0 console. LED1 blinks with the
  sampler, LED2 is on while Wi-Fi is up. Wi-Fi drops reconnect with the same `seq` counter; the sampler never stops.
- **ADC.** SAADC channel 0 on AIN0 (`P0.04`, the DK's "A0"), gain 1/3 with the internal 0.6 V reference → 0–1.8 V, 12-bit,
  10 µs acquisition. Period is in RTC ticks (32768 Hz), so rates are `32768/N` — default N=4 → 8192 Hz; N=2 → 16 kHz for
  dolphin clicks. `fs` is measured from block timestamps and written into the header, so the receiver never needs N.
- **Analog front end (1.8 V rail).** The Darlington follower does not fit two Vbe drops in 1.8 V and the SAADC does not need
  it (accepts sources ≤ ~200 kΩ at 10 µs; the piezo stack is ~3.5 kΩ at 500 Hz), so it is passive: 10k/10k mid-rail divider
  + 10 µF, 470k bias into the piezo, 10k series into AIN0 with the pin clamps absorbing knocks. `dc=` should read 0.8–1.0 V.
- **Configuration.** `keiko.conf` is Kconfig (`CONFIG_KEIKO_WIFI_SSID`, `_PSK`, `_UDP_HOST` — default `255.255.255.255`
  subnet broadcast so any laptop on the hotspot just listens — `_UDP_PORT`, `_NODE_ID`, `_SAMPLE_PERIOD_TICKS`). Overridable
  per build: `make flash SSID=hotspot PSK=secret UDP_HOST=10.0.0.5`. `Kconfig` declares the options; the packed header
  struct has a `BUILD_ASSERT` on its 26-byte size and `host/test_node.py` checks the Python side against the same layout.
- **No board yet?** `make sim` emits the identical stream from a Mac (`host/sim_node.py`); `make test` checks the packet
  format offline. `make sdk` installs nrfutil + the toolchain (~4 GB); the Makefile wraps `west` in
  `nrfutil sdk-manager toolchain launch` if it is not on PATH.

</details>

<details>
<summary><b>Elastic — Find the Signal</b> · <code>elastic/</code></summary>

Elasticsearch is where the stream stops being audio and becomes something you can ask questions of. Everything below is
provisioned by one script (`setup.py`) against an Elastic Cloud trial and fed live by `pipeline … --elastic`.

**Indices** (index templates in `mappings/`):

| index | one doc per | notable fields |
|---|---|---|
| `keiko-windows` | classifier window (every 1.5 s) | `label`, `whale`, `confidence`, dynamic `probs.*` (22 class probabilities), `audio.rms_db/peak_hz/centroid_hz/bandwidth_hz/flatness`, `net.*` packet loss, `location` `geo_point`, `in_event` |
| `keiko-detections` | event | `species`, `confidence`, `duration_s`, `location` + `buoy_location` `geo_point`, `fix.{err_m,method,arrivals[]}` from the TDOA solve, `embedding` `dense_vector` 512-d cosine, `description` `semantic_text` (ELSER), `track_id` |

**Write path.** `keiko_es.py` builds the docs (`window_doc`, `detection_doc`, `describe`) and bulk-writes through a buffered
writer so the pipeline's 1.5 s loop never blocks on the network. `features.py` computes the spectral descriptors per window and
takes the CNN's pooled 512-d activations (mean‖max over the last conv block) as the embedding — the same tensor the classifier
uses, so "sounds like" is in the model's own feature space. `describe` writes a plain-English paragraph per event for
ELSER to embed ("Confident humpback whale call (0.91) at buoy KEIKO-01 Saturday 20 September 2026 07:35 UTC in the early
morning. Lasted 4.5 s over 3 classifier windows. Low frequency, tonal sound: peak 410 Hz, centroid 520 Hz, level −38 dBFS."),
so "long low moan at night" finds it.
`backfill.py` replays `pipeline/out/events.jsonl` + `site/data/detections.csv` through the same path, re-running the CNN on
each clip for the embedding.

**Read paths.**
- **ES|QL** — `queries.esql` holds 11 queries: what's on the water now, detections per 15 min per buoy, soundscape floor vs
  whale share, hour-of-day, the right-whale question, per-buoy stream loss, the classifier's second guesses, sound character per
  species, centroid of fixes and distance from the harbour entrance, low-confidence windows, field vs synthetic.
- **kNN** — `ask.py --similar <id>` runs a `knn` query on `embedding` to find the events that sound most like a given one.
- **Semantic** — `ask.py --semantic "long low tonal call at night"` runs a `semantic` query on `description` (ELSER).
- **ML** — `setup.py` creates the `keiko-soundscape` anomaly-detection job + datafeed over `keiko-windows` (level jumps,
  unusual spectral character); `ask.py --anomalies` lists its records.
- **Alerting** — an ES|QL rule every minute: `FROM keiko-detections | WHERE species == "North Atlantic right whale" AND
  confidence >= 0.7 …` → webhook connector to Discord/Slack ("slow to 10 kn"). NOAA's seasonal management areas are the reason
  the buoys exist; this is the *action*.
- **Kibana** — `kibana/dashboard.md` is the six-panel Lens recipe (all ES|QL panels) plus data views created by `setup.py`.
- **Agent** — `ask.py "<question>"` gives Claude (`claude-opus-5`) both index schemas, an ES|QL cheat sheet and three tools
  (`esql`, `similar_sounds`, `semantic_search`); it writes the query, runs it, and answers. Guarded to read-only `FROM keiko-*`
  queries. `-v` prints every query it tries.

Without ML nodes (`setup.py --no-elser --no-ml`) `description` degrades to `text` and `--semantic` to a `match` query.
Unit + integration tests: `test_elastic.py`.

</details>

<details>
<summary><b>Voloridge — Signal in the Noise</b> · <code>training/voloridge/</code></summary>

Two uses of what Voloridge hands out: their AWS instances for training, and NOAA ISD from their curated dataset list for
the insight.

**1. Training on Voloridge compute.** The whale CNN's laptop run is width 32, ~25 s/epoch, and the 5.1 GB v2 tensor set
barely fits in RAM. On a Voloridge `g5` (Amazon Linux 2023, `us-east-1`) the plan in `configs/pretrain_gpu.json` is width 64,
40 epochs, batch 256, then 4 more seeds (dolphin genera sit at F1 0.0–0.2 on one seed, so seed variance matters), a
`--no_merge_rare` run to see whether the 4 rare species come back with capacity, and `train/finetune.py` transfers the
pretrained model to our own Charles River / Boston Harbor recordings (`data/charles_v2`: motorboat / crew shell / ambient /
rain / unknown; stem + blocks 0–1 frozen). `infra/` is the plumbing: `check.sh` (ssh, `nvidia-smi`, disk, IAM role),
`bootstrap_instance.sh` (dnf, venv, torch cu12, boto3, Voloridge's tools), `sync_up.sh` / `sync_down.sh` (rsync code + tensors
up, `runs/` + `models/` down), `remote.sh run <name> <cmd>` (detached tmux per run, `make logs RUN=…`). Outputs are the same
`runs/<name>/{best.pt,test_metrics.json}` + `models/*.pt` layout as `training/whale_cnn/train.py`, so
`keiko_pipeline.py --model` takes any of them unchanged. Everything is `voloridge.env` (host, user, key — not committed).

**2. NOAA ISD ⋈ hydrophone noise floor.** Boston Logan (USAF 725090 / WBAN 14739, 6 km from the buoy) reports wind,
pressure, precip hourly. The question: how much of the underwater background is weather?
- `data/fetch_isd.sh` uses Voloridge's own `noaa_isd/fetch.py` (synced from `s3://voloridge-hack-mit-2026/src`, read for free
  through the instance's `AmazonS3ReadOnlyAccess` role + S3 gateway endpoint) to pull the station's years from `s3://noaa-isd-pds`.
- `data/parse_isd.py` parses the fixed-width records — mandatory section (wind dir/speed, temp, dew point, SLP, visibility) +
  the `AA1` precipitation group — drops rows with failing QC codes, resamples to the hour.
- **Archive lag found on 2026-09-20:** the public ISD archive (S3 and NCEI) ends 2025-08-27 for Logan and has no 2026 prefix.
  ISD is the archive of the ASOS/METAR reports the NWS API serves live, so `data/fetch_nws.py` pulls
  `api.weather.gov/stations/KBOS/observations` for the recording window, maps it onto the same columns, and merges with a
  `source` column (`isd` / `nws`) — same instrument, same station, hours old instead of a year.
- `analysis/noise_floor.py` computes the 30th-percentile band level in 10–1000 Hz per recording (the same `floor` statistic
  the live pipeline reports) and buckets it hourly UTC; `analysis/join_isd.py` inner-joins on the hour and reports Spearman
  correlation of floor vs wind speed, precip, and pressure tendency, plus a partial residual after removing the diurnal
  boat-traffic cycle → `analysis/out/noise_vs_weather.{csv,png}` + `summary.json`.
- Status: parser, NWS fetch, floor and join all run on real data (2,067 KBOS obs, 16 field clips → 2 buoy-hours; the join
  refuses < 4 hours, so the stats were exercised on a synthetic floor over the real weather series). The insight needs hours
  of recording spanning a wind change.

</details>

## Wire protocols

<details>
<summary><b>KEIK</b> — node → pipeline UDP datagram (all three nodes)</summary>

One datagram per block, little-endian, 26-byte header:

```
magic 4s "KEIK" | ver B 1 | node B | fmt B 0=int16 raw ADC | bits B | fs f Hz | seq I | t_ns Q | n H | n×int16
```

`node`: 0 = UNO Q, 1 = ESP32-S3 / nRF7002 (`KEIKO_NODE_ID`). `bits`: 14 / 12 / 12. `fs` is *measured* by the sender from MCU
timestamps, so the receiver never needs the nominal period. `t_ns` is host arrival time on the UNO Q and node uptime on the
Wi-Fi nodes — good enough for single-node work; multi-node TDOA needs a shared clock (SNTP over the same link is the next
step). The pipeline keys streams by `node`, detects gaps from `seq`, and reports loss as `net.dropped_packets`.

</details>

<details>
<summary><b>KBLK</b> — ESP32-S3 → laptop serial frame (USB mode only)</summary>

```
magic 4s "KBLK" | seq I | t0_us I | dropped I | n H | n×int16 raw ADC 0..4095 | crc H (CRC-16/CCITT-FALSE over everything before it)
```

Resynchronised on the magic if a byte is lost; `python/main.py` re-emits each valid frame as a `KEIK` datagram with `bits=12`.

</details>

<details>
<summary><b>WebSocket</b> — pipeline → server → browsers (<code>server/keiko_server.py</code>, <code>site/lib/feed.ts</code>)</summary>

Clients send `{"role": "node"}` (pipeline) or `{"role": "browser"}` first. Node → server messages carry a `type`:
`telemetry`, `audio` (256 samples + 80 spectrogram bins, ~15/s), `window` (one per classifier window), `detection`.
Server → browser: the same plus `hello` (buoys, recent detections, tracks), `buoys`, `track`, `status`; `detection` gains a
`fix` (`lat`, `lon`, `err_m`, `arrivals[]`, `simulated_buoys[]`) and a `track_id`.

**Localization.** One physical buoy cannot fix a position, so the server completes the array with two *virtual* buoys
(`KEIKO-02`/`-03`, ~350 m up- and down-channel, flagged `simulated` everywhere — dashed on the map, `SIM` in the arrivals
table). A hidden source (random walk, 1–2 m/s) gives true arrival times; the real buoy's arrival is the event time, the virtual
ones get 2 ms jitter. The fix itself is a genuine TDOA solve: multi-start Gauss-Newton on the hyperbolic residuals at 1480 m/s,
with a 2σ error radius from timing noise mapped through the geometry. Over 300 simulated calls: median 3.7 m from the hidden
source, truth inside the radius 96 % of the time. Consecutive fixes of one species within 10 min form a track (`T001`, …).

</details>

<details>
<summary><b>Detection database</b> — <code>site/data/</code> (plain files, published with the site)</summary>

`detections.csv` is the source of truth (`id, buoy_id, timestamp_utc, latitude, longitude, confidence, species, peak_hz,
duration_s, sample_rate_hz, clip_path, spectrogram_path, source ∈ {field, replay, synthetic}, notes`), `detections.json` the typed
copy the site reads, `buoys.csv` the registry, `clips/<id>.wav` 16-bit mono PCM, `spectrograms/<id>.png` a 0–1 kHz mel
spectrogram in the site's colour ramp with quiet bins transparent, `schema.json` a JSON Schema. `site/tools/keiko_data.py add|rebuild|synth`
maintains it; `pipeline … --archive` calls `add` per event. Readable straight from
`https://raw.githubusercontent.com/2900xt/keiko-hackMIT/main/site/data/detections.csv`.

</details>

## Models

<details>
<summary><b>Whale CNN v2</b> — the classifier the pipeline runs · <code>training/whale_cnn/</code></summary>

- **Data.** `training/dataset/` is a unified SQLite of 126,563 clips / ~99 h / 59 species from nine public sources (Watkins
  WHOI, ReefSet, ToadFishFinder, Cornell/Kaggle right-whale challenge, BEANS HICEAS minke, Orcasound Pod.Cast, three Zenodo
  fish sets) plus a literature-derived catalogue of 75 datasets and 122 call types. `scripts/extract_features_v2.py` makes
  71,522 × (128 × 301) float16 log-mel windows in 22 classes: species for baleen + non-dolphin toothed whales, **genus** for
  dolphins, `other_baleen` / `other_toothed`, `no_whale_noise` (ambient, vessels, detector negatives), `no_whale_biophony`
  (fish, seals, reef). Splits are by **recording group** (tape / fold / site / date), so no session leaks; big classes capped
  at 6k windows spread across up to 147 groups; z-scored per recording.
- **Model.** Stem (avg-pool 2 + 5×5 stride-2 conv) → 4 blocks (32→64→128→256, 2× conv3×3 + BN + ReLU + max-pool) → mean‖max
  global pool → dropout 0.5 → linear. ~1.2 M params, input `(B,1,128,301)`. Class-balanced sampling, SpecAugment, **random
  bandwidth masking** (so recorder sample rate cannot be a cue — v1's 0.99 on fin/minke/right was exactly that shortcut), mixup,
  label smoothing, AdamW + one-cycle, early stop on val macro-F1. Exported as `.pt` + `.onnx` (`log_mel` → `logits`).
- **Numbers (test).** Window macro-F1 0.45, clip-level 0.44, hierarchy (baleen / toothed / no-whale) 0.87. Right whale 0.96,
  common minke 0.88, fin 0.83, bowhead 0.82, blue 0.80, orca 0.80, humpback 0.62. Non-*Delphinus* dolphin genera 0.0–0.2.
- **Abstain rule** (`predict.py`, used by the pipeline at `--min_conf 0.8 --margin 0.2`): false alarms on no-whale windows
  0.02, whales missed 0.61, species accuracy on kept windows 0.36 — the pipeline additionally needs ≥ 2 consecutive windows.
  Lower to `0.6 / 0.2` for a demo with real calls (FA 0.19, missed 0.32).

</details>

<details>
<summary><b>Moby / Keiko right-whale ensemble</b> · <code>training/moby/</code></summary>

PyTorch port of the ISEF *MobyGlobal* two-branch model: a 2D branch (Conv2d 1→16→32→64→128 + CBAM on a 103×126 stack of
log-mel‖MFCC‖chroma‖spectral-contrast) and a 1D branch (Conv1d 7→64→128 + BiLSTM(64) over RMS, centroid, bandwidth, rolloff,
flatness, ZCR, YIN f0), concat 384 → 256 → 64 → 2, K-fold ensemble by mean softmax. ~358k params per fold. Trained on the
30,000 Cornell/Kaggle clips (2 s @ 2 kHz, 7,027 NARW upcalls): test AUROC **0.9766** (poster 0.977, Cornell baseline 0.72).
`models/keiko.pt` adds 3,073 Watkins baleen windows grouped by tape: AUROC 0.9816 overall, 0.9750 Kaggle-only, recall 1.0 on
held-out Watkins tapes. Exported as one ONNX graph (`x2d`, `x1d` → `p_whale`).

</details>

<details>
<summary><b>Whale location table</b> · <code>training/location/</code></summary>

`whale_locations.csv`: 48k real detection events with sensor position + UTC time, from Watkins (11,225 cuts → 214
recording-day events, note-parsed positions cross-checked to 2°), DCLDE 2027 killer-whale annotations (34,423 calls at 23 fixed
hydrophones, ecotype labels), and the AAD Antarctic blue/fin library (77,080 calls at 10 moorings). Plus `whale_presence_daily.csv`
(site × species × date) and `sites.csv` (170 sensors). Presence-only; supports occupancy / seasonal models, not trajectories.

</details>

## Repository layout

| path | what |
|---|---|
| `firmware/unoq/` | Arduino UNO Q node: Zephyr sketch (MCU) + App Lab Python (Linux), `keiko.env`, Makefile over adb/ssh |
| `firmware/esp32-s3/` | ESP32-S3 DevKitC-1 node: USB-CDC `KBLK` frames or Wi-Fi `KEIK` datagrams, laptop forwarder |
| `firmware/nrf7002/` | nRF7002 DK node: nRF Connect SDK app, Kconfig settings, simulator, host tools |
| `firmware/uno-q-hydrophone/` | the first App Lab experiment: `analogRead(A0)` loudness bar (superseded by `unoq/`) |
| `pipeline/` | `keiko_pipeline.py` (UDP → CNN → events → sinks), `replay_wav.py`, `live.sh`/`demo.sh`, `usb_relay.py`, `netinfo.py`, tests |
| `server/` | `keiko_server.py`: WebSocket hub, TDOA localization, tracks, `--inject` fake detections |
| `elastic/` | Elasticsearch layer: index templates (geo, dense_vector, ELSER), `--elastic` ingest, ML anomaly job + alert rule setup, ES\|QL library, kNN/semantic search, `ask.py` (Claude ⇄ ES\|QL agent) |
| `site/` | Next.js 16 static export: landing, live map (Leaflet), waveform + spectrogram canvases, detection database UI; `data/` is the database; `tools/keiko_data.py` |
| `training/dataset/` | marine sound database builder (SQLite + audio), feature extractors, literature survey |
| `training/whale_cnn/` | the classifier: `train.py`, `predict.py`, `models/whale_cnn_v2.*` |
| `training/moby/` | right-whale two-branch ensemble |
| `training/voloridge/` | GPU training on Voloridge AWS + NOAA ISD noise-floor join |
| `training/location/` | real whale detection × position × time table |
| `hardware/` | `hydrophone-cup/` potting mold, `buoy-v2/` OpenSCAD hull for the ESP32 + Codex reviews, `buoy-3d/`, `buoy-sla/` STLs |
| `.github/workflows/pages.yml` | builds `site/` (with `data/`) and deploys to GitHub Pages on push to `main` |

## How to run

All Python except the firmware-local venvs uses one repo venv at `.venv/` (torch, librosa, soundfile, scipy, …, ~2 GB):

```bash
cd pipeline && make venv
```

<details open>
<summary><b>No hardware: test + demo</b></summary>

```bash
cd pipeline && make test          # ~15 s: white noise → 0 events, humpback sample → a humpback event
```

```bash
cd pipeline && make demo          # loops 38 s of NPS humpback song through replay_wav.py as if a node were streaming
```

Expect `WHALE Megaptera_novaeangliae` every 1.5 s during song and `EVENT … humpback whale` when a bout ends.
`CLIP=path make demo` for any WAV/FLAC/MP3. `make demo ARGS="--archive --source replay"` also writes the events into
`site/data/`; `ARGS="--elastic"` indexes them; `ARGS="--server ws://127.0.0.1:8765"` feeds the map.

</details>

<details>
<summary><b>Full local stack: server + site + demo</b></summary>

```bash
cd pipeline && make server                                # ws://0.0.0.0:8765 (or `make server ARGS="--inject 6"` for fake detections)
```

```bash
cd site && npm install && npm run dev                     # http://localhost:3000 · /app/ is the live map + database
```

```bash
cd pipeline && make demo ARGS="--server ws://127.0.0.1:8765"
```

The Live tab falls back to a synthetic feed after 4 s without a server and switches to the real one when it appears. The
static build (GitHub Pages) has no server; set `NEXT_PUBLIC_KEIKO_WS` at build time to point a deployed site at one.

</details>

<details>
<summary><b>Arduino UNO Q node (USB-C, no Wi-Fi needed)</b></summary>

```bash
cd firmware/unoq && make core     # once: arduino-cli + arduino:zephyr core (~1 GB, includes adb)
```

```bash
cd firmware/unoq && make start && make logs     # push app over adb, compile + flash on the board, start Python; first run ~2 min
```

Health line should show `fs= 3333.3Hz … dc=1.71V`. Then, on a phone hotspot shared by board and laptop:

```bash
make -C firmware/unoq wifi SSID='<hotspot>' PSK='<password>'
```

```bash
cd pipeline && make live          # netinfo.py picks the laptop IP, retargets the node (hot reload, no restart), runs the pipeline
```

No usable network at all: `VIA=usb make live` relays the stream over the USB cable. `make record DURATION=30` pulls a WAV
to `recordings/`; `make -C firmware/unoq retarget UDP_HOST=auto` sends the stream back to the board itself.

</details>

<details>
<summary><b>ESP32-S3 node</b></summary>

```bash
cd firmware/esp32-s3 && make core          # once: arduino-cli + esp32:esp32 core (~600 MB)
```

```bash
cd firmware/esp32-s3 && make flash && make start   # port labelled USB (not UART); health line, blocks → udp 127.0.0.1:5005
```

```bash
cd pipeline && ../.venv/bin/python keiko_pipeline.py --port 5005     # in another terminal
```

Wi-Fi mode (no laptop): `cp sketch/wifi_config.h.example sketch/wifi_config.h`, fill in SSID/PSK/pipeline IP, `make flash`.
`make start UDP_HOST=<ip>` forwards to another machine in USB mode.

</details>

<details>
<summary><b>nRF7002 DK node</b></summary>

```bash
cd firmware/nrf7002 && make sdk            # once: nrfutil + nRF Connect SDK v3.0 toolchain into ~/ncs (~4 GB)
```

```bash
cd firmware/nrf7002 && make flash SSID='<hotspot>' PSK='<password>' && make monitor   # J-Link USB port; console shows wifi: up, ip …
```

```bash
cd pipeline && make live-nrf               # the node broadcasts to the subnet by default; this just listens on :5005 as KEIKO-02
```

No board: `make sim` in one terminal, `make live-nrf` in another. `make retarget UDP_HOST=<ip>` is a reflash here.

</details>

<details>
<summary><b>Elastic</b></summary>

1. Elastic Cloud trial → create a deployment (ML on by default) → API key with write access.
2. `cp elastic/.env.example elastic/.env`; fill `ELASTIC_URL` (or `ELASTIC_CLOUD_ID`), `ELASTIC_API_KEY`, `KIBANA_URL`,
   `ANTHROPIC_API_KEY` (for `ask.py`), optionally `KEIKO_WEBHOOK_URL`.

```bash
.venv/bin/pip install -r elastic/requirements.txt
```

```bash
cd elastic && ../.venv/bin/python setup.py && ../.venv/bin/python backfill.py && ../.venv/bin/python setup.py --status
```

```bash
cd pipeline && make demo ARGS="--elastic"           # or make live ARGS="--elastic"; combine with --server / --archive freely
```

```bash
cd elastic && ../.venv/bin/python ask.py -v "is the noise floor at KEIKO-01 higher tonight than this afternoon?"
```

`ask.py --similar <id>` · `--semantic "…"` · `--anomalies` · `--esql '<query>'` run without an LLM. Dashboard recipe:
`elastic/kibana/dashboard.md`. Self-hosted without ML: `setup.py --no-elser --no-ml`.

</details>

<details>
<summary><b>Voloridge</b></summary>

GPU box (instance details from the booth into `training/voloridge/voloridge.env`):

```bash
cd training/voloridge && make check && make bootstrap && make sync-up && make pretrain && make logs RUN=volo_w64
```

```bash
cd training/voloridge && make finetune && make sync-down     # after pretrain; needs `make charles-features` first
```

ISD + noise floor (no GPU, runs anywhere; needs `boto3 matplotlib` on top of the pipeline venv):

```bash
cd training/voloridge && make all-local    # = tools → isd → isd-parse → nws → noise-floor → join  → analysis/out/noise_vs_weather.*
```

</details>

<details>
<summary><b>Training from scratch</b></summary>

```bash
cd training/dataset && ./fetch_data.sh && python3 scripts/build_db.py && python3 scripts/extract_features_v2.py   # ~20 GB raw, 5.1 GB tensors
```

```bash
cd training/whale_cnn && python train.py --features ../dataset/features/v2_32k_mel128_3s --epochs 25 --patience 5 --export models/whale_cnn_v2
```

```bash
cd training/moby && python3 features.py && python3 train.py --features ../dataset/features/moby_narw_watkins.npz --out models/keiko.pt
```

`python predict.py file.wav --min_conf 0.8` in either folder classifies any recording (resamples itself).

</details>

<details>
<summary><b>Site deploy</b></summary>

Push to `main` touching `site/**` runs `.github/workflows/pages.yml`: `npm ci && npm run build` (which copies `data/` into
`public/data/` first) with `NEXT_PUBLIC_BASE_PATH` set from `configure-pages`, then uploads `site/out/`. Locally:
`npm run build && npm start`.

</details>

## Tests

| what | command |
|---|---|
| pipeline regression (noise → 0 events, humpback → event) | `cd pipeline && make test` |
| Elastic doc shapes, features, query guard + cluster round-trip | `cd elastic && ../.venv/bin/python test_elastic.py` |
| UNO Q Python side with synthetic blocks | `cd firmware/unoq && make venv && make test` |
| ESP32-S3 Python side with synthetic frames | `cd firmware/esp32-s3 && make venv && make test` |
| nRF7002 packet layout via the simulator | `cd firmware/nrf7002 && make test` |
| firmware compile checks without a board | `make check` (unoq, esp32-s3) · `make build` (nrf7002) |
| site types | `cd site && npm run typecheck` |
