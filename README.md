# Keiko — HackMIT 2026

Hydrophones on the Charles River that turn underwater sound into a live, searchable stream of what's happening on the water. Built by [Moby Labs](https://github.com/2900xt) at HackMIT 2026.

```
hydrophone A ──> nRF7002 DK ─────┐  (SAADC → UDP/Wi-Fi)
                                  ├──> Arduino UNO Q (Linux side, Python):
hydrophone B ──> ESP32-S3 DevKitC ┘     detector → classifier → embedding → TDOA → Elasticsearch
                                                                     │
                                          Kibana dashboard · ES|QL + kNN agent · alerting
```

## Layout

- `firmware/esp32-s3/` — hydrophone B: I2S/ADC capture → UDP stream
- `firmware/nrf7002/` — hydrophone A: SAADC capture → UDP stream (Zephyr / nRF Connect SDK)
- `firmware/unoq/` — hydrophone C: UNO Q's own MCU samples a piezo → Bridge → UDP (see its README for the analog front end)
- `pipeline/` — Python: UDP receiver, detector, classifier, embeddings, TDOA, Elasticsearch ingest
- `elastic/` — index mappings, Kibana saved objects, ES|QL queries, agent
- `training/` — dataset prep + model training scripts
- `hardware/` — buoy enclosure: OpenSCAD source, STLs, print previews, design review notes
- `site/` — public website (Next.js, static export): live map of whale detections across buoys (draft, one buoy on synthetic data)

## Team

Taha Rawjani ([@2900xt](https://github.com/2900xt)) · Matthew Li ([@Mallhw](https://github.com/Mallhw))
