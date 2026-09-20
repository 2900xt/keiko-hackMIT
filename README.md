# Keiko — HackMIT 2026

Hydrophones in Boston Harbor that turn underwater sound into a live, searchable stream of what's happening on the water. Built by [Moby Labs](https://github.com/2900xt) at HackMIT 2026.

```
hydrophone A ──> nRF7002 DK ─────┐  (SAADC → UDP/Wi-Fi)
                                  ├──> Arduino UNO Q (Linux side, Python):
hydrophone B ──> ESP32-S3 DevKitC ┘     detector → classifier → embedding → TDOA → Elasticsearch
                                                                     │
                                          Kibana dashboard · ES|QL + kNN agent · alerting
```

## Layout

- `firmware/esp32-s3/` — hydrophone B: ESP32-S3 DevKitC samples a piezo at 8 kHz → USB (laptop forwards UDP) or, with Wi-Fi credentials compiled in, UDP straight from the board (see its README)
- `firmware/nrf7002/` — hydrophone A: SAADC capture → UDP stream (Zephyr / nRF Connect SDK)
- `firmware/unoq/` — hydrophone C: UNO Q's own MCU samples a piezo → Bridge → UDP (see its README for the analog front end)
- `pipeline/` — Python: UDP receiver, detector, classifier, embeddings, TDOA, Elasticsearch ingest
- `elastic/` — index mappings, Kibana saved objects, ES|QL queries, agent
- `training/` — dataset prep + model training scripts
- `hardware/` — buoy enclosure: OpenSCAD source, STLs, print previews, design review notes
- `server/` — central server: localizes each detection across the buoy array (TDOA; two of the three buoys are simulated), keeps tracks, streams to the site over a WebSocket
- `site/` — public website (Next.js, static export): live map of whale detections across buoys (draft, one buoy on synthetic data)

## Try it

```bash
cd pipeline && make venv && make test && make demo      # no hardware: humpback song -> detections
```

```bash
cd firmware/unoq && make start && make logs            # UNO Q on USB-C: flash the node, watch the health line
```

```bash
cd firmware/esp32-s3 && make flash && make start      # ESP32-S3 on USB: flash the node, watch the health line
```

```bash
cd pipeline && make live                               # node -> this laptop over Wi-Fi -> whale CNN -> events
```

`make live ARGS="--archive"` writes detections into `site/data/`, which the website reads. Details in
`pipeline/README.md`, `firmware/unoq/README.md` and `firmware/esp32-s3/README.md`.

## Team

Taha Rawjani ([@2900xt](https://github.com/2900xt)) · Matthew Li ([@Mallhw](https://github.com/Mallhw))
