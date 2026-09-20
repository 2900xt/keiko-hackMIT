# Keiko buoy site

Website + detection database for the Keiko buoys. The database is the `data/` folder (see `data/README.md`); the site reads it directly, so publishing this folder with GitHub Pages gives one URL for both.

Plain HTML/CSS/JS, no build. One buoy in the Charles River off MIT, on synthetic data.

```sh
python3 -m http.server 8080   # then open http://localhost:8080
```

- `index.html` — Live tab (map, buoy status, mel spectrogram) and Database tab (every detection: time, location, confidence, spectrogram thumbnail, audio clip)
- `style.css` — white, Helvetica
- `synthetic.js` — fake feed: `telemetry` every 2 s, `audio` (spectrogram column) 20×/s, `detection` when a call ends
- `app.js` — draws it; Database tab loads `data/detections.json` and appends live detections
- `data/` — the detection database: CSV + JSON, one WAV clip and one PNG spectrogram per detection
- `tools/keiko_data.py` — add a detection from a WAV, rebuild the JSON, or generate synthetic rows

To go live, replace `createFeed()` with a WebSocket client that emits the same three events. Detection rows render their spectrogram and WAV clip from the call parameters (`f0`, `sweep`, `duration_s`); a real backend would ship a clip URL and a precomputed thumbnail instead.
