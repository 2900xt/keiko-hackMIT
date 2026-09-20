# Keiko central server

One Python process between the pipeline and the website: it takes each detection the pipeline hears, localizes
it across the buoy array, groups fixes into tracks, and streams everything (telemetry, live audio, "hearing now",
detections with fixes, tracks) to every open browser over a WebSocket.

```
pipeline ──ws──►  keiko_server.py  ──ws──►  site (Live tab)
 --server                │
                    TDOA fix + tracks
```

## Run

```bash
cd pipeline && make server                     # ws://0.0.0.0:8765 (needs the pipeline venv: websockets)
cd pipeline && make live ARGS="--server ws://127.0.0.1:8765"    # or make demo ARGS=... without a board
cd site && npm run dev                          # the Live tab connects to ws://localhost:8765 in dev
```

`make server ARGS="--inject 6"` fakes a humpback every 6 s so the map can be worked on without a pipeline.

The site's static build (GitHub Pages) has no server and keeps its synthetic feed; set `NEXT_PUBLIC_KEIKO_WS`
at build time to point a deployed site at a reachable server. In `npm run dev` the page falls back to the
synthetic feed after 4 s without a server and switches to the real one when it appears.

## Localization — what is real and what is not

One physical buoy cannot fix a position. The server completes the array with two **virtual buoys**
(`KEIKO-02`, `KEIKO-03`, ~350 m up- and down-channel on the far side, flagged `simulated` everywhere they
appear — dashed on the map, `SIM` in the arrivals table, named in the rail's footnote).

For each detection a hidden source position (a random walk in the channel, 1–2 m/s) gives the true arrival
time at each buoy; the real buoy's arrival is the event time, the virtual ones get 2 ms of jitter. The **fix
is a genuine TDOA solve** — multi-start Gauss-Newton on the hyperbolic residuals at 1480 m/s, with an error
radius from the timing noise mapped through the geometry (2σ). Only two of the three arrival times are made up.
Over 300 simulated calls the solve lands a median 3.7 m from the hidden source and the truth is inside the
reported radius 96 % of the time.

Tracks: consecutive fixes of the same species within 10 min form one track (`T001`, …), drawn as a polyline.

## Protocol

Clients send `{"role": "node"}` (pipeline) or `{"role": "browser"}` first. Node → server messages carry a
`type`: `telemetry`, `audio` (256 samples + 80 bins, ~15/s), `window` (one per classifier window), `detection`.
Server → browser: the same plus `hello` (buoys, recent detections, tracks), `buoys`, `track`, `status`;
`detection` gains a `fix` object (`lat`, `lon`, `err_m`, `arrivals[]`, `simulated_buoys[]`) and a `track_id`,
and its `lat`/`lon` become the fix. `site/lib/feed.ts` documents the browser-side shapes.
