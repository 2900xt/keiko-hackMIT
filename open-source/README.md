# Keiko buoy site

Website + detection database for the Keiko buoys. The database is the `data/` folder (see `data/README.md`); the site reads it directly, so publishing this folder with GitHub Pages gives one URL for both.

Next.js (App Router, TypeScript), exported as a static site. One buoy in the Charles River off MIT, on synthetic data.

```sh
npm install
npm run dev      # http://localhost:3000
npm run build    # static export to out/, with data/ copied in
```

- `app/` — `layout.tsx` (metadata, favicon), `page.tsx`, `globals.css` (white, Helvetica)
- `components/`
  - `KeikoApp.tsx` — owns the feed, the detection list, the `#live` / `#db` hash route, and table state
  - `LiveView.tsx` — map cell + buoy rail; `MapView.tsx` (Leaflet, client-only), `Spectrogram.tsx` (scrolling mel canvas + level bar)
  - `DatabaseView.tsx` — summary tiles, `DetectionsChart.tsx` (14-day SVG bars), filter chips, sortable table of `DetectionRow.tsx` (time, location, confidence, spectrogram thumbnail, audio clip)
- `lib/`
  - `feed.ts` — synthetic feed: `telemetry` every 2 s, `audio` (spectrogram column) 20×/s, `detection` when a call ends
  - `detections.ts` — detection types, archive + buoy loaders, time helpers
  - `dsp.ts` — magma colormap, mel scale, and the thumbnail / WAV a live row renders from its call parameters
  - `hooks.ts` — `useFeedEvent`, `useNow`, `useAudioLevel`, `useElementSize`, `usePlayer`
- `public/data` — symlink to `../data` so the dev server serves the database; `npm run build` copies the real folder into `out/data`
- `data/` — the detection database: CSV + JSON, one WAV clip and one PNG spectrogram per detection
- `tools/keiko_data.py` — add a detection from a WAV, rebuild the JSON, or generate synthetic rows

Deployment: `.github/workflows/pages.yml` builds with `NEXT_PUBLIC_BASE_PATH` set to the Pages base path (`/keiko-hackMIT` for the project site, empty for a custom domain) and uploads `out/`.

To go live, replace `createFeed()` in `lib/feed.ts` with a WebSocket client that emits the same three events. Detection rows render their spectrogram and WAV clip from the call parameters (`f0`, `sweep`, `duration_s`); a real backend would ship a clip URL and a precomputed thumbnail instead.
