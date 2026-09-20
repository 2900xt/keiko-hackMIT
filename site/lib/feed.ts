// Synthetic buoy feed. Same event shapes a real buoy would send.
//   telemetry: { id, ts, lat, lon, battery_pct, water_temp_c, uptime_s }   every 2 s
//   audio:     { ts, pcm, samples, bins, level_db }                          20 / s
//              pcm is the new signal since the last frame (50 ms at 2 kHz), so
//              frames concatenate into a gapless stream; samples is the trailing
//              128 ms window the oscilloscope draws
//   detection: { id, ts, lat, lon, confidence, f0, sweep, duration_s }        when a call ends
//
// To go live, replace createFeed() with a WebSocket client that emits the same
// three events.

export interface Buoy { id: string; lat: number; lon: number }

export interface Telemetry {
  id: string; ts: string; lat: number; lon: number;
  battery_pct: number; water_temp_c: number; uptime_s: number;
}
export interface AudioFrame {
  ts: string;
  pcm: Float32Array;     // AUDIO_HOP new samples at AUDIO_RATE, contiguous frame to frame
  samples: Float32Array; // trailing window of AUDIO_WINDOW samples, for the scope
  bins: Float32Array;    // 80 mel bins, 0–1 kHz, 0..1
  level_db: number;
}
export interface LiveDetection {
  id: string; ts: string; lat: number; lon: number;
  confidence: number; f0: number; sweep: number; duration_s: number;
}

export interface FeedEvents { telemetry: Telemetry; audio: AudioFrame; detection: LiveDetection }
export type FeedHandler<K extends keyof FeedEvents> = (payload: FeedEvents[K]) => void;

export interface Feed {
  buoy: Buoy;
  synthetic: boolean; // true while the feed is generated in the browser; the UI says so
  on<K extends keyof FeedEvents>(type: K, fn: FeedHandler<K>): () => void;
  start(): void;
  stop(): void;
  backfill(n: number): LiveDetection[];
}

const rand = (a: number, b: number) => a + Math.random() * (b - a);
const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

// Charles River basin, just off the MIT Sailing Pavilion.
export const BUOY: Buoy = { id: "KEIKO-01", lat: 42.3572, lon: -71.0868 };
export const AUDIO_RATE = 2000;  // Hz
export const AUDIO_HOP = 100;     // samples per frame (50 ms)
export const AUDIO_WINDOW = 256;  // samples the scope shows (128 ms)
const NSAMP = AUDIO_WINDOW, NBINS = 80;

interface Call { f0: number; sweep: number; amp: number; t0: number; t1: number }

export function createFeed(): Feed {
  const handlers: { [K in keyof FeedEvents]?: FeedHandler<K>[] } = {};
  const st = { batt: rand(80, 95), temp: rand(17, 19), uptime: Math.floor(rand(3600, 36000)), call: null as Call | null, phase: 0 };
  const samples = new Float32Array(NSAMP), pcm = new Float32Array(AUDIO_HOP), bins = new Float32Array(NBINS);
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
    // Synthesise the next AUDIO_HOP samples with a running tone phase, so the
    // chunks are gapless when played back to back, then roll them into the window.
    const dphi = 2 * Math.PI * f / AUDIO_RATE;
    for (let i = 0; i < AUDIO_HOP; i++) {
      st.phase += dphi;
      if (st.phase > 2 * Math.PI) st.phase -= 2 * Math.PI;
      pcm[i] = (Math.random() - 0.5) * 0.25 + env * Math.sin(st.phase);
    }
    samples.copyWithin(0, AUDIO_HOP);
    samples.set(pcm, NSAMP - AUDIO_HOP);
    let rms = 0;
    for (let i = 0; i < NSAMP; i++) rms += samples[i] * samples[i];
    for (let i = 0; i < NBINS; i++) bins[i] = (0.22 * (1 - i / NBINS) + 0.06) * rand(0.5, 1.5);
    if (c) {
      const b = clamp(Math.round(f / 1000 * NBINS), 0, NBINS - 1);
      bins[b] = Math.min(1, bins[b] + env);
      if (b > 0) bins[b - 1] = Math.min(1, bins[b - 1] + env * 0.5);
      if (b < NBINS - 1) bins[b + 1] = Math.min(1, bins[b + 1] + env * 0.5);
    }
    const level = 20 * Math.log10(Math.sqrt(rms / NSAMP) + 1e-6) - 20;
    emit("audio", { ts: new Date().toISOString(), pcm, samples, bins, level_db: +level.toFixed(1) });
  }

  let seq = 0;
  // Position the sighting near the buoy but inside the river: the Charles runs
  // roughly NE–SW here (bearing 60°), ~500 m wide, so spread along the axis
  // and keep the across-axis offset small.
  function place() {
    const along = rand(-450, 450), across = rand(-110, 110); // metres
    const ax = Math.sin(60 * Math.PI / 180), ay = Math.cos(60 * Math.PI / 180);
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
    telemetry();
    timers = [setInterval(telemetry, 2000), setInterval(audio, 50)];
  }
  function stop() { timers.forEach(clearInterval); timers = []; }

  return { on, start, stop, backfill, buoy: BUOY, synthetic: true };
}
