# Keiko Whale Network — website (rough draft)

A public map of whale detections reported by Keiko acoustic buoys. The end goal is one page that shows every buoy we deploy and where whales have been heard around each of them.

This first draft shows **one buoy streaming synthetic data** so the layout, map, and data contract can be reviewed before any real hardware is online. Nothing on the page is a real whale.

## Run it

No build step. It is plain HTML/CSS/JS with [Leaflet](https://leafletjs.com) loaded from a CDN.

```sh
cd open-source
python3 -m http.server 8080
# open http://localhost:8080
```

Opening `index.html` directly from the file system also works.

## What is on the page

- **Map** (Esri Ocean basemap, darkened to fit the theme): the buoy with a pulsing marker, its detection range, and every detection in the last 30 minutes as an orange dot that fades with age. Click a dot for species, confidence, bearing/range, and call frequency.
- **Buoy card**: position, battery, water temperature, radio signal, noise floor, uptime, heartbeat. Status flips to `stale` / `offline` if heartbeats stop.
- **Hydrophone**: a scrolling spectrogram (0–1 kHz) fed by the audio stream. Whale calls show up as harmonic stacks; a random broadband transient plays the role of a passing boat.
- **Last hour**: detection counts by species.
- **Detections**: live feed, newest first.
- **Pause** freezes the stream so a screenshot is easy.

## Files

```
open-source/
├── index.html              page skeleton
├── css/style.css           theme + layout (dark, responsive)
├── js/synthetic-stream.js  fake buoy: telemetry, spectrogram, detections
└── js/app.js               map, spectrogram canvas, sidebar wiring
```

## Data contract

`app.js` only knows about four event types. `synthetic-stream.js` emits them on timers; a real buoy backend should emit the same shapes over a WebSocket or SSE connection, and nothing in the UI has to change.

| event       | payload                                                                                                                        | cadence          |
|-------------|--------------------------------------------------------------------------------------------------------------------------------|------------------|
| `hello`     | `{ buoy: { id, name, lat, lon, range_km, hydrophone, sample_rate_hz } }`                                                       | once             |
| `telemetry` | `{ buoy_id, ts, lat, lon, battery_pct, water_temp_c, rssi_dbm, noise_floor_db, uptime_s }`                                     | every 2 s        |
| `audio`     | `{ buoy_id, ts, bins: Float32Array }` — one spectrogram column, values 0..1, low frequency first                                | 10 / s           |
| `detection` | `{ id, buoy_id, ts, species, common_name, confidence, bearing_deg, range_km, lat, lon, peak_hz, duration_s }`                  | every 5–18 s     |

All `ts` values are ISO-8601 UTC strings.

### How the synthetic data is made

- 1–3 "virtual whales" wander around the buoy in polar coordinates. Each detection samples one of them and adds bearing/range noise, so the map shows plausible tracks rather than random confetti.
- Species are weighted (humpback 42%, fin 25%, right whale 18%, minke 15%) and each has a frequency band and call duration used for both the detection record and the spectrogram harmonics.
- Confidence falls with range.
- Ten back-dated detections are generated on load so the "last hour" panel is not empty.

The example buoy sits on Stellwagen Bank in Massachusetts Bay, which is real whale habitat and is where the first field unit would most plausibly go.

## Next steps

- [ ] Multiple buoys: `hello` per buoy, marker cluster, per-buoy sidebar on click.
- [ ] Real backend: WebSocket that replays the Elasticsearch `detections` index from `pipeline/`.
- [ ] Time scrubber for the last 24 h / 7 d instead of the fixed 30-minute fade.
- [ ] Species filter and a per-species colour.
- [ ] Deploy with GitHub Pages from this folder.
