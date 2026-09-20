# Keiko — Kibana dashboard

`setup.py` creates the data views, the ML job and the alert rule through the API. The dashboard itself is six
Lens panels; each is an **ES|QL** panel (Dashboard → Add panel → ES|QL) with the query below — about ten minutes
to lay out. Set the time picker to *Last 24 hours* with 10 s auto-refresh for the demo.

| # | Panel (type) | Query |
|---|---|---|
| 1 | **Detections by species** (bar, stacked, `t` on x, `n` on y, split by `species`) | `queries.esql` #2 but `BY species, t = BUCKET(@timestamp, 15 minutes)` |
| 2 | **Where** (Maps: layer from data view *Keiko detections*, field `location`, colour by `species`, tooltip `confidence`, `fix.err_m`) | — (Maps app, not Lens) |
| 3 | **Soundscape** (line, `level_db` and `p95_db` on y, `t` on x, split by `buoy_id`) | `queries.esql` #3 |
| 4 | **Whale share of windows** (area, `whale_share` on y) | `queries.esql` #3 |
| 5 | **Hour of day** (bar, `hour` on x, `n` on y) | `queries.esql` #4 |
| 6 | **Stream health** (metric, `loss_pct` per `buoy_id`) | `queries.esql` #6 |
| 7 | **Anomalies** (ML → Anomaly Explorer → job `keiko-soundscape` → *Add to dashboard* swimlane) | — |
| 8 | **Latest detections** (Discover saved search on *Keiko detections*, columns `@timestamp buoy_id species confidence duration_s audio.peak_hz`) | — |

## Alerting

`setup.py` creates **Keiko: North Atlantic right whale** — an ES|QL rule every minute over the last 5 minutes:

```
FROM keiko-detections | WHERE species == "North Atlantic right whale" AND confidence >= 0.7
| KEEP @timestamp, id, buoy_id, confidence, duration_s, location | SORT @timestamp DESC
```

With `KEIKO_WEBHOOK_URL` set it posts to a Discord/Slack webhook ("slow to 10 kn"). Add more rules the same way:
noise-floor jump (`FROM keiko-windows | WHERE audio.rms_db > -20`), stream loss (`net.dropped_packets > 0`), or
an ML rule on `keiko-soundscape` with anomaly score ≥ 75.

## Discover tricks

- ES|QL mode: paste any block from `queries.esql`.
- "Sounds like this": `python3 ask.py --similar <id>` — kNN is not in Lens, so the demo shows it from the CLI or the agent.
- "Long low moan at night": `python3 ask.py --semantic "..."` (ELSER over `description`).
