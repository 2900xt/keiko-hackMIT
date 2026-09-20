# Keiko buoy site

Plain HTML/CSS/JS, no build. One buoy in the Charles River off MIT, on synthetic data.

```sh
python3 -m http.server 8080   # then open http://localhost:8080
```

- `index.html` — three panels: live map, buoy status, live hydrophone
- `style.css` — white, Helvetica
- `synthetic.js` — fake feed: `telemetry` every 2 s, `audio` (waveform + spectrogram column) 20×/s
- `app.js` — draws it

To go live, replace `createFeed()` with a WebSocket client that emits the same two events.
