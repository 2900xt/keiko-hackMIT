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
// createFeed() connects to NEXT_PUBLIC_KEIKO_WS (in `npm run dev`: ws://localhost:8765) and falls back to the
// synthetic generator when no server answers; the static build has no server and is always synthetic.

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
  synthetic: boolean; // true when created without a server URL; see the status event for the live state
  on<K extends keyof FeedEvents>(type: K, fn: FeedHandler<K>): () => void;
  start(): void;
  stop(): void;
  backfill(n: number): LiveDetection[];
}

const rand = (a: number, b: number) => a + Math.random() * (b - a);
const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

// Boston Harbor: President Roads, between Deer Island and Long Island.
export const BUOY: Buoy = { id: "KEIKO-01", lat: 42.34, lon: -70.97 };
const NSAMP = 256, NBINS = 80;

interface Call { f0: number; sweep: number; amp: number; t0: number; t1: number }

export function createSyntheticFeed(): Feed {
  const handlers: { [K in keyof FeedEvents]?: FeedHandler<K>[] } = {};
  const st = { batt: rand(80, 95), temp: rand(17, 19), uptime: Math.floor(rand(3600, 36000)), call: null as Call | null };
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
    // occasional tonal event: boat hum or a whale-like sweep
    if (!st.call && Math.random() < 0.02) {
      st.call = { f0: rand(80, 400), sweep: rand(-150, 150), amp: rand(0.4, 0.8), t0: t, t1: t + rand(1500, 5000) };
    }
    if (st.call && t > st.call.t1) { emit("detection", finish(st.call)); st.call = null; }
    const c = st.call, ph = c ? (t - c.t0) / (c.t1 - c.t0) : 0;
    const f = c ? c.f0 + c.sweep * ph : 0;
    const env = c ? Math.sin(ph * Math.PI) * c.amp : 0;
    let rms = 0;
    for (let i = 0; i < NSAMP; i++) {
      const noise = (Math.random() - 0.5) * 0.25;
      const tone = env * Math.sin(2 * Math.PI * f * (t / 1000 + i / 2000));
      samples[i] = noise + tone;
      rms += samples[i] * samples[i];
    }
    for (let i = 0; i < NBINS; i++) bins[i] = (0.22 * (1 - i / NBINS) + 0.06) * rand(0.5, 1.5);
    if (c) {
      const b = clamp(Math.round(f / 1000 * NBINS), 0, NBINS - 1);
      bins[b] = Math.min(1, bins[b] + env);
      if (b > 0) bins[b - 1] = Math.min(1, bins[b - 1] + env * 0.5);
      if (b < NBINS - 1) bins[b + 1] = Math.min(1, bins[b + 1] + env * 0.5);
    }
    const level = 20 * Math.log10(Math.sqrt(rms / NSAMP) + 1e-6) - 20;
    emit("audio", { ts: new Date().toISOString(), samples, bins, level_db: +level.toFixed(1) });
  }

  let seq = 0;
  // Position the sighting uniformly within 450 m of the buoy: open water, no
  // shoreline to stay inside of.
  function place() {
    const r = 450 * Math.sqrt(Math.random()), a = rand(0, 2 * Math.PI); // metres, radians
    const east = r * Math.sin(a), north = r * Math.cos(a);
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
      ...place(),
    };
  }
  // A few back-dated detections so the database is not empty on load.
  function backfill(n: number) {
    const out: LiveDetection[] = [];
    for (let i = 0; i < n; i++) {
      const t0 = Date.now() - rand(3, 120) * 60000, dur = rand(1500, 5000);
      out.push(finish({ f0: rand(80, 400), sweep: rand(-150, 150), amp: rand(0.4, 0.8), t0, t1: t0 + dur }));
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

  return { on, start, stop, backfill, buoy: BUOY, synthetic: true };
}

// ---- the real thing: server/keiko_server.py over a WebSocket -----------------
const FALLBACK_AFTER_MS = 4000; // no server within this: run the synthetic feed until one appears

export function createLiveFeed(url: string): Feed {
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
    fallback = createSyntheticFeed();
    const types: (keyof FeedEvents)[] = ["buoys", "telemetry", "audio", "detection"];
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

  return { on, start, stop, backfill: () => [], buoy: BUOY, synthetic: false };
}

export function createFeed(): Feed {
  const url = process.env.NEXT_PUBLIC_KEIKO_WS ?? (process.env.NODE_ENV === "development" ? "ws://localhost:8765" : "");
  return url ? createLiveFeed(url) : createSyntheticFeed();
}
