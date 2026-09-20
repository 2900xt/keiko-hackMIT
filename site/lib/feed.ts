// Buoy feed: the same event shapes whether they come from the central server
// (server/keiko_server.py over a WebSocket) or are generated in the browser.
//   buoys:     Buoy[]                                                    the array, on connect and when it changes
//   telemetry: { id, ts, lat, lon, battery_pct?, water_temp_c?, uptime_s?, simulated? }   every 2 s per buoy
//   audio:     { ts, samples: Float32Array, bins: Float32Array, level_db }  ~15-20 / s, the real buoy's hydrophone
//   window:    { ts, label, species?, conf, whale }                      one per classifier window ("hearing now")
//   detection: { id, ts, lat, lon, confidence, ..., species?, fix? }     when a call ends; lat/lon is the fix when there is one
//   track:     { id, species, points[] }                                 after each detection, the track it joined
//   status:    { connected, node_online, synthetic }                    link state
//
// createFeed(site) connects to NEXT_PUBLIC_KEIKO_WS (in `npm run dev`: ws://localhost:8765) and falls back to the
// synthetic generator when no server answers; the static build has no server and is always synthetic. The site
// (lib/sites.ts) says where the buoy sits and what the generator should sound like: whale-like tonal calls in
// Boston Harbor, motorboats and crew shells on the Charles.
import type { Site } from "./sites";

export interface Buoy { id: string; lat: number; lon: number; simulated?: boolean }

export interface Telemetry {
  id: string; ts: string; lat: number; lon: number;
  battery_pct?: number; water_temp_c?: number; uptime_s?: number; simulated?: boolean;
}
export interface AudioFrame { ts: string; samples: Float32Array; bins: Float32Array; level_db: number }
export interface Hearing { ts: string; label: string; species?: string | null; conf: number; whale: boolean; in_event?: boolean }
export interface Arrival { buoy_id: string; dt_ms: number; range_m: number; simulated: boolean }
export interface Fix {
  lat: number; lon: number; err_m: number; method: "tdoa"; c_m_s: number;
  arrivals: Arrival[]; simulated_buoys: string[];
}
export interface LiveDetection {
  id: string; ts: string; lat: number; lon: number;
  confidence: number; f0: number; sweep: number; duration_s: number;
  buoy_id?: string; species?: string; fix?: Fix; track_id?: string;
}
export interface Track { id: string; species: string; started: string; points: { ts: string; lat: number; lon: number; err_m: number; id: string }[] }
export interface Status { connected: boolean; node_online: boolean; synthetic: boolean }

export interface FeedEvents {
  buoys: Buoy[]; telemetry: Telemetry; audio: AudioFrame; window: Hearing;
  detection: LiveDetection; track: Track; status: Status;
}
export type FeedHandler<K extends keyof FeedEvents> = (payload: FeedEvents[K]) => void;

export interface Feed {
  buoy: Buoy;         // the physical buoy this page is "about" (its telemetry drives the rail)
  site: Site;         // where the demo is set (lib/sites.ts); the server decides for itself when one is connected
  synthetic: boolean; // true when created without a server URL; see the status event for the live state
  on<K extends keyof FeedEvents>(type: K, fn: FeedHandler<K>): () => void;
  start(): void;
  stop(): void;
  backfill(n: number): LiveDetection[];
}

const rand = (a: number, b: number) => a + Math.random() * (b - a);
const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

const NSAMP = 256, NBINS = 80, SR = 2000;   // samples per frame, spectrogram bins over 0-1 kHz, waveform rate

// One simulated sound event. Harbor: a tonal, whale-like sweep (f0 + sweep over the call). Charles: river traffic,
// a motorboat pass (f0 = engine/prop hum fundamental, harmonics above it, broadband wash) or a crew shell (a
// broadband catch every `period` ms, ~32 strokes a minute, nothing tonal at all). `kind` becomes the species.
interface Call { kind: string; f0: number; sweep: number; amp: number; t0: number; t1: number; period?: number }

// A soundscape decides when events start, what they sound like in a frame, and where on the water they are placed.
interface Soundscape {
  start(t: number): Call | null;                 // called each frame while idle
  frame(c: Call | null, t: number, samples: Float32Array, bins: Float32Array): void;
  label(c: Call | null): string;                 // the classifier window label when this is what is heard
}

function whaleSoundscape(): Soundscape {
  return {
    start(t) {
      if (Math.random() >= 0.02) return null;
      return { kind: "tonal call", f0: rand(80, 400), sweep: rand(-150, 150), amp: rand(0.4, 0.8), t0: t, t1: t + rand(1500, 5000) };
    },
    frame(c, t, samples, bins) {
      const ph = c ? (t - c.t0) / (c.t1 - c.t0) : 0;
      const f = c ? c.f0 + c.sweep * ph : 0;
      const env = c ? Math.sin(ph * Math.PI) * c.amp : 0;
      for (let i = 0; i < NSAMP; i++) {
        samples[i] = (Math.random() - 0.5) * 0.25 + env * Math.sin(2 * Math.PI * f * (t / 1000 + i / SR));
      }
      for (let i = 0; i < NBINS; i++) bins[i] = (0.22 * (1 - i / NBINS) + 0.06) * rand(0.5, 1.5);
      if (c) {
        const b = clamp(Math.round(f / 1000 * NBINS), 0, NBINS - 1);
        bins[b] = Math.min(1, bins[b] + env);
        if (b > 0) bins[b - 1] = Math.min(1, bins[b - 1] + env * 0.5);
        if (b < NBINS - 1) bins[b + 1] = Math.min(1, bins[b + 1] + env * 0.5);
      }
    },
    label: (c) => c ? c.kind : "no_whale",
  };
}

function riverSoundscape(): Soundscape {
  // Background the buoy hears all the time: wind that gusts (a random walk), wake and chop slapping the hull,
  // and distant traffic, a far-off boat drone that comes and goes without ever being close enough to count.
  let wind = 1.0, gustTarget = 1.0, splash = 0;
  let far = { f0: rand(45, 90), amp: 0, target: rand(0.1, 0.35), hold: 0 };
  return {
    start(t) {
      if (Math.random() >= 0.016) return null;   // a pass every few seconds: a busy stretch of river
      const r = Math.random();
      if (r < 0.55) {
        // outboard / launch: 60-140 Hz fundamental that drops a little as it goes by (Doppler), 5-14 s
        return { kind: "motorboat", f0: rand(60, 140), sweep: 0, amp: rand(0.6, 1.0), t0: t, t1: t + rand(5000, 14000) };
      }
      if (r < 0.72) {
        // a bigger, slower launch or the tour boat: low fundamental, long pass, loud
        return { kind: "motorboat", f0: rand(30, 60), sweep: 0, amp: rand(0.8, 1.0), t0: t, t1: t + rand(12000, 22000) };
      }
      // eight: a catch every 1.6-2.1 s, 8-16 s in range
      return { kind: "crew shell", f0: rand(70, 110), sweep: 0, amp: rand(0.4, 0.7), t0: t, t1: t + rand(8000, 16000), period: rand(1600, 2100) };
    },
    frame(c, t, samples, bins) {
      // wind: wanders toward a target that jumps now and then (gusts and lulls)
      if (Math.random() < 0.01) gustTarget = rand(0.55, 1.8);
      wind += (gustTarget - wind) * 0.03 + rand(-0.03, 0.03);
      // chop and wake against the hull: frequent short slaps, bigger when the wind is up
      if (Math.random() < 0.02 * wind) splash = Math.max(splash, rand(0.3, 0.9) * Math.min(1.4, wind));
      // distant traffic: a drone that swells, holds and fades, then picks a new boat
      if (far.hold-- <= 0) { far.target = Math.random() < 0.3 ? 0 : rand(0.1, 0.4); far.hold = rand(100, 500); if (far.target === 0) far.f0 = rand(45, 90); }
      far.amp += (far.target - far.amp) * 0.02;
      const breathe = 1 + 0.15 * Math.sin(t / 1900) + 0.08 * Math.sin(t / 700);
      const floor = 0.26 * wind * breathe + splash;
      const ph = c ? clamp((t - c.t0) / (c.t1 - c.t0), 0, 1) : 0;
      const pass = c ? Math.pow(Math.sin(ph * Math.PI), 0.6) * c.amp : 0;   // approaches, passes, fades
      let hum = 0, thump = 0, wash = 0, f0 = 0;
      if (c && c.kind === "motorboat") {
        f0 = c.f0 * (1 + 0.05 * (1 - 2 * ph)) * (1 + 0.01 * Math.sin(t / 230));   // pitch falls through the pass, throttle wobbles
        hum = pass; wash = 0.45 * pass;              // cavitation lifts the whole band
      } else if (c && c.period) {
        const sp = ((t - c.t0) % c.period) / c.period;   // stroke phase: catch, drive, recovery
        thump = sp < 0.08 ? pass * (1 - sp / 0.08) : 0;
        wash = sp < 0.45 ? 0.3 * pass : 0.08 * pass;
      }
      for (let i = 0; i < NSAMP; i++) {
        const tt = t / 1000 + i / SR;
        let v = (Math.random() - 0.5) * (floor + wash + thump * 1.5);
        if (hum) for (let k = 1; k <= 5; k++) v += (hum / k) * 0.45 * Math.sin(2 * Math.PI * f0 * k * tt);
        if (far.amp > 0.01) for (let k = 1; k <= 3; k++) v += (far.amp / k) * 0.3 * Math.sin(2 * Math.PI * far.f0 * k * tt);
        samples[i] = v;
      }
      for (let i = 0; i < NBINS; i++) {
        const pink = 0.28 * Math.pow(1 - i / NBINS, 1.6) + 0.05;
        bins[i] = pink * floor / 0.16 * rand(0.55, 1.45) + wash * rand(0.6, 1.2) + (i < 20 ? thump * (1 - i / 20) : 0);
      }
      const addHarmonics = (f: number, a: number, n: number) => {
        for (let k = 1; k <= n; k++) {
          const b = Math.round(f * k / 1000 * NBINS);
          if (b >= NBINS) break;
          bins[b] += a / Math.sqrt(k);
          if (b > 0) bins[b - 1] += a / Math.sqrt(k) * 0.35;
          if (b < NBINS - 1) bins[b + 1] += a / Math.sqrt(k) * 0.35;
        }
      };
      if (hum) addHarmonics(f0, hum, 7);
      if (far.amp > 0.01) addHarmonics(far.f0, far.amp * 0.8, 3);
      for (let i = 0; i < NBINS; i++) bins[i] = Math.min(1, bins[i]);
      splash = Math.max(0, splash - 0.1);
    },
    label: (c) => c ? c.kind : "ambient",
  };
}

export function createSyntheticFeed(site: Site): Feed {
  const BUOY = site.buoy;
  const handlers: { [K in keyof FeedEvents]?: FeedHandler<K>[] } = {};
  const st = { batt: rand(80, 95), temp: rand(17, 19), uptime: Math.floor(rand(3600, 36000)), call: null as Call | null, nextWindow: 0 };
  const scape = site.soundscape === "river" ? riverSoundscape() : whaleSoundscape();
  const samples = new Float32Array(NSAMP), bins = new Float32Array(NBINS);
  let timers: ReturnType<typeof setInterval>[] = [];

  function on<K extends keyof FeedEvents>(type: K, fn: FeedHandler<K>) {
    const list = (handlers[type] ??= []) as FeedHandler<K>[];
    list.push(fn);
    return () => { const i = list.indexOf(fn); if (i >= 0) list.splice(i, 1); };
  }
  function emit<K extends keyof FeedEvents>(type: K, payload: FeedEvents[K]) {
    ((handlers[type] ?? []) as FeedHandler<K>[]).forEach((fn) => fn(payload));
  }

  function telemetry() {
    st.batt = clamp(st.batt - rand(0.002, 0.01), 0, 100);
    st.temp = clamp(st.temp + rand(-0.02, 0.02), 5, 28);
    st.uptime += 2;
    emit("telemetry", {
      id: BUOY.id, ts: new Date().toISOString(),
      lat: BUOY.lat + rand(-0.00004, 0.00004), lon: BUOY.lon + rand(-0.00004, 0.00004),
      battery_pct: +st.batt.toFixed(1), water_temp_c: +st.temp.toFixed(2), uptime_s: st.uptime,
    });
  }

  function audio() {
    const t = Date.now();
    if (!st.call) st.call = scape.start(t);
    if (st.call && t > st.call.t1) { emit("detection", finish(st.call)); st.call = null; }
    scape.frame(st.call, t, samples, bins);
    let rms = 0;
    for (let i = 0; i < NSAMP; i++) rms += samples[i] * samples[i];
    const level = 20 * Math.log10(Math.sqrt(rms / NSAMP) + 1e-6) - 20;
    emit("audio", { ts: new Date().toISOString(), samples, bins, level_db: +level.toFixed(1) });
    // one classifier window every 1.5 s: what the buoy is hearing right now. Nothing here is a whale.
    if (t >= st.nextWindow) {
      st.nextWindow = t + 1500;
      const c = st.call;
      emit("window", { ts: new Date(t).toISOString(), label: scape.label(c), species: null, whale: false, in_event: !!c,
                       conf: +clamp(c ? 0.55 + c.amp * 0.4 + rand(-0.06, 0.06) : rand(0.82, 0.97), 0.4, 0.99).toFixed(2) });
    }
  }

  let seq = 0;
  // Position the event in the channel: spread along its axis, a smaller spread across it, so a river's
  // sightings stay in the river and a harbor's stay in the shipping lane.
  function place() {
    const { bearing_deg, half_len_m, half_width_m } = site.channel;
    const along = rand(-half_len_m, half_len_m), across = rand(-half_width_m, half_width_m); // metres
    const ax = Math.sin(bearing_deg * Math.PI / 180), ay = Math.cos(bearing_deg * Math.PI / 180);
    const east = along * ax + across * ay, north = along * ay - across * ax;
    return {
      lat: +(BUOY.lat + north / 111320).toFixed(5),
      lon: +(BUOY.lon + east / (111320 * Math.cos(BUOY.lat * Math.PI / 180))).toFixed(5),
    };
  }
  function finish(c: Call): LiveDetection {
    const dur = (c.t1 - c.t0) / 1000;
    return {
      id: BUOY.id + "-" + (++seq).toString(36) + "-" + c.t0.toString(36),
      ts: new Date(c.t0).toISOString(),
      confidence: +clamp(0.45 + c.amp * 0.55 + rand(-0.08, 0.08), 0.4, 0.99).toFixed(2),
      f0: Math.round(c.f0), sweep: Math.round(c.sweep), duration_s: +dur.toFixed(1),
      species: site.soundscape === "river" ? c.kind : undefined,
      ...place(),
    };
  }
  // A few back-dated detections so the database is not empty on load.
  function backfill(n: number) {
    const out: LiveDetection[] = [];
    for (let i = 0; i < n; i++) {
      const t0 = Date.now() - rand(3, 120) * 60000;
      let c = scape.start(t0);
      while (!c) c = scape.start(t0);
      out.push(finish({ ...c, t0, t1: t0 + (c.t1 - c.t0) }));
    }
    return out.sort((a, b) => a.ts.localeCompare(b.ts));
  }

  function start() {
    if (timers.length) return;
    emit("buoys", [BUOY]);
    emit("status", { connected: true, node_online: true, synthetic: true });
    telemetry();
    timers = [setInterval(telemetry, 2000), setInterval(audio, 50)];
  }
  function stop() { timers.forEach(clearInterval); timers = []; }

  return { on, start, stop, backfill, buoy: BUOY, site, synthetic: true };
}

// ---- the real thing: server/keiko_server.py over a WebSocket -----------------
const FALLBACK_AFTER_MS = 4000; // no server within this: run the synthetic feed until one appears

export function createLiveFeed(url: string, site: Site): Feed {
  const handlers: { [K in keyof FeedEvents]?: FeedHandler<K>[] } = {};
  let ws: WebSocket | null = null, running = false, everConnected = false, retry = 1000;
  let timer: ReturnType<typeof setTimeout> | null = null, fallbackTimer: ReturnType<typeof setTimeout> | null = null;
  let fallback: Feed | null = null, unsubs: (() => void)[] = [];
  let nodeOnline = false;

  function on<K extends keyof FeedEvents>(type: K, fn: FeedHandler<K>) {
    const list = (handlers[type] ??= []) as FeedHandler<K>[];
    list.push(fn);
    return () => { const i = list.indexOf(fn); if (i >= 0) list.splice(i, 1); };
  }
  function emit<K extends keyof FeedEvents>(type: K, payload: FeedEvents[K]) {
    ((handlers[type] ?? []) as FeedHandler<K>[]).forEach((fn) => fn(payload));
  }
  function status(connected: boolean) {
    emit("status", { connected, node_online: connected && nodeOnline, synthetic: !!fallback });
  }

  function startFallback() {
    if (fallback || !running) return;
    fallback = createSyntheticFeed(site);
    const types: (keyof FeedEvents)[] = ["buoys", "telemetry", "audio", "window", "detection"];
    unsubs = types.map((t) => fallback!.on(t, (p) => emit(t, p as never)));
    fallback.start();
  }
  function stopFallback() {
    if (!fallback) return;
    unsubs.forEach((u) => u()); unsubs = [];
    fallback.stop(); fallback = null;
  }

  function handle(msg: Record<string, unknown>) {
    const type = msg.type as string;
    if (type === "hello") {
      nodeOnline = !!msg.node_online;
      emit("buoys", msg.buoys as Buoy[]);
      for (const d of (msg.detections as LiveDetection[]) ?? []) emit("detection", d);
      for (const t of (msg.tracks as Track[]) ?? []) emit("track", t);
      status(true);
    } else if (type === "status") {
      nodeOnline = !!msg.node_online; status(true);
    } else if (type === "audio") {
      emit("audio", { ts: msg.ts as string, samples: Float32Array.from(msg.samples as number[]), bins: Float32Array.from(msg.bins as number[]), level_db: msg.level_db as number });
    } else if (type === "telemetry" || type === "window" || type === "detection" || type === "track" || type === "buoys") {
      emit(type, msg as never);
    }
  }

  function connect() {
    if (!running) return;
    try { ws = new WebSocket(url); } catch { schedule(); return; }
    ws.onopen = () => {
      everConnected = true; retry = 1000;
      if (fallbackTimer) { clearTimeout(fallbackTimer); fallbackTimer = null; }
      stopFallback();
      ws?.send(JSON.stringify({ role: "browser" }));
    };
    ws.onmessage = (e) => { try { handle(JSON.parse(e.data)); } catch { /* ignore malformed */ } };
    ws.onclose = () => { ws = null; status(false); if (everConnected) startFallback(); schedule(); };
    ws.onerror = () => { ws?.close(); };
  }
  function schedule() {
    if (!running || timer) return;
    timer = setTimeout(() => { timer = null; connect(); }, retry);
    retry = Math.min(retry * 2, 10000);
  }

  function start() {
    if (running) return;
    running = true;
    status(false);
    fallbackTimer = setTimeout(() => { fallbackTimer = null; if (!everConnected) startFallback(); }, FALLBACK_AFTER_MS);
    connect();
  }
  function stop() {
    running = false;
    if (timer) { clearTimeout(timer); timer = null; }
    if (fallbackTimer) { clearTimeout(fallbackTimer); fallbackTimer = null; }
    stopFallback();
    ws?.close(); ws = null;
  }

  return { on, start, stop, backfill: () => [], buoy: site.buoy, site, synthetic: false };
}

export function createFeed(site: Site): Feed {
  const url = process.env.NEXT_PUBLIC_KEIKO_WS ?? (process.env.NODE_ENV === "development" ? "ws://localhost:8765" : "");
  return url ? createLiveFeed(url, site) : createSyntheticFeed(site);
}
