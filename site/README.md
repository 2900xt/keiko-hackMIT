# Keiko buoy site

Website + detection database for the Keiko buoys. The database is the `data/` folder (see `data/README.md`); the site reads it directly, so publishing this folder with GitHub Pages gives one URL for both.

Next.js (App Router, TypeScript), exported as a static site. One buoy in the Charles River off MIT, on synthetic data.

```sh
npm install
npm run dev      # http://localhost:3000
npm run build    # static export to out/, data/ included
```

- `app/` — `layout.tsx` (metadata, favicon), `page.tsx`, `globals.css` (dark navy, blue accent, IBM Plex Sans + Mono via `next/font`)
- `components/`
  - `KeikoApp.tsx` — owns the feed, the detection list, the `#live` / `#db` hash route, and table state
  - `LiveView.tsx` — map cell + buoy rail on top, sound strip below; `MapView.tsx` (Leaflet, client-only), `Waveform.tsx` (raw-signal oscilloscope + level bar, bottom left), `Spectrogram.tsx` (scrolling mel canvas, bottom right)
  - `DatabaseView.tsx` — summary tiles, `DetectionsChart.tsx` (14-day SVG bars), filter chips, sortable table of `DetectionRow.tsx` (time, location, confidence, spectrogram thumbnail, audio clip)
- `lib/`
  - `feed.ts` — synthetic feed: `telemetry` every 2 s, `audio` (spectrogram column) 20×/s, `detection` when a call ends; `feed.synthetic` is true, and the buoy rail says so (set it false in a real client)
  - `detections.ts` — detection types, archive + buoy loaders, time helpers
  - `dsp.ts` — magma colormap, mel scale, and the thumbnail / WAV a live row renders from its call parameters
  - `hooks.ts` — `useFeedEvent`, `useNow`, `useAudioLevel`, `useElementSize`, `usePlayer`
- `public/data` — copy of `data/` made by `npm run dev` and `npm run build` (gitignored), so the dev server and the static export both serve the database
- `data/` — the detection database: CSV + JSON, one WAV clip and one PNG spectrogram per detection
- `tools/keiko_data.py` — add a detection from a WAV, rebuild the JSON, or generate synthetic rows

Deployment: `.github/workflows/pages.yml` builds with `NEXT_PUBLIC_BASE_PATH` set to the Pages base path (`/keiko-hackMIT` for the project site, empty for a custom domain) and uploads `out/`.

To go live, replace `createFeed()` in `lib/feed.ts` with a WebSocket client that emits the same three events. Detection rows render their spectrogram and WAV clip from the call parameters (`f0`, `sweep`, `duration_s`); a real backend would ship a clip URL and a precomputed thumbnail instead.
