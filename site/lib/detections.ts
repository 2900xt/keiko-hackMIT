import type { LiveDetection } from "./feed";

export const DATA_BASE = "data/"; // the GitHub database, relative to this page
export const DAY = 86400000;
export const RANGE_M = 300; // nominal hydrophone detection range, drawn as the ring on the map

// One row of the site's detection list: either archived (from data/detections.json,
// with a clip URL and a precomputed spectrogram) or live this session (drawn and
// synthesised from the call parameters f0 / sweep / duration_s).
export interface Detection {
  id: string;
  buoy_id: string;
  ts: string;          // ISO-8601 UTC, start of the call
  t: number;           // ts as epoch ms
  lat: number;
  lon: number;
  confidence: number;  // 0–1
  f0: number;          // Hz
  sweep: number;       // Hz over the call
  duration_s: number;
  live: boolean;
  source?: string;     // "field" | "synthetic" for archived rows
  spectrogram?: string;
  clip?: string;
}

// A row of data/detections.json (see data/schema.json).
export interface ArchiveRow {
  id: string; buoy_id: string; timestamp_utc: string; latitude: number; longitude: number;
  confidence: number; species?: string; peak_hz?: number; duration_s: number; sample_rate_hz?: number;
  clip_path: string; spectrogram_path: string; source: "field" | "synthetic"; notes?: string;
}
export interface Archive { generated_utc: string; count: number; detections: ArchiveRow[] }

export interface BuoyInfo { hydrophone: string; sample_rate_hz: number; deployed_utc: string }

export function fromArchive(r: ArchiveRow): Detection {
  return {
    id: r.id, buoy_id: r.buoy_id, ts: r.timestamp_utc, t: Date.parse(r.timestamp_utc),
    lat: r.latitude, lon: r.longitude, confidence: r.confidence,
    f0: r.peak_hz || 0, sweep: 0, duration_s: r.duration_s, live: false, source: r.source,
    spectrogram: DATA_BASE + r.spectrogram_path, clip: DATA_BASE + r.clip_path,
  };
}

export function fromLive(d: LiveDetection, buoyId: string, live: boolean): Detection {
  return { ...d, buoy_id: buoyId, t: Date.parse(d.ts), live };
}

export async function loadArchive(): Promise<Archive> {
  const r = await fetch(DATA_BASE + "detections.json");
  if (!r.ok) throw new Error(String(r.status));
  return r.json();
}

export async function loadBuoy(id: string): Promise<BuoyInfo | null> {
  const r = await fetch(DATA_BASE + "buoys.csv");
  if (!r.ok) throw new Error(String(r.status));
  const [head, ...rows] = (await r.text()).trim().split("\n").map((l) => l.split(","));
  const row = rows.find((x) => x[head.indexOf("buoy_id")] === id);
  if (!row) return null;
  return {
    hydrophone: row[head.indexOf("hydrophone")],
    sample_rate_hz: +row[head.indexOf("sample_rate_hz")],
    deployed_utc: row[head.indexOf("deployed_utc")],
  };
}

export const ago = (ms: number) =>
  ms < 1500 ? "just now"
  : ms < 60000 ? Math.round(ms / 1000) + " s ago"
  : ms < 3600000 ? Math.round(ms / 60000) + " min ago"
  : ms < DAY ? Math.round(ms / 3600000) + " h ago"
  : Math.round(ms / DAY) + " d ago";

// [number, unit] for the "Last call" stat
export const agoParts = (ms: number): [number, string] =>
  ms < 60000 ? [Math.round(ms / 1000), "s ago"]
  : ms < 3600000 ? [Math.round(ms / 60000), "min ago"]
  : ms < DAY ? [Math.round(ms / 3600000), "h ago"]
  : [Math.round(ms / DAY), "d ago"];

export function median(xs: number[]): number | null {
  if (!xs.length) return null;
  const c = xs.slice().sort((a, b) => a - b), n = c.length;
  return n % 2 ? c[(n - 1) / 2] : (c[n / 2 - 1] + c[n / 2]) / 2;
}

// "140 m NE of buoy": where a detection sits relative to a buoy, for readers
// who cannot place a coordinate pair on the river by eye.
export function offsetFrom(origin: { lat: number; lon: number }, p: { lat: number; lon: number }) {
  const north = (p.lat - origin.lat) * 111320;
  const east = (p.lon - origin.lon) * 111320 * Math.cos(origin.lat * Math.PI / 180);
  const m = Math.hypot(north, east);
  if (m < 15) return "at the buoy";
  const deg = (Math.atan2(east, north) * 180 / Math.PI + 360) % 360;
  const dir = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][Math.round(deg / 45) % 8];
  const dist = m < 1000 ? Math.round(m / 10) * 10 + " m" : (m / 1000).toFixed(1) + " km";
  return dist + " " + dir + " of buoy";
}

export function ageOpacity(t: number, now = Date.now()) {
  const days = (now - t) / DAY;
  return days < 1 ? 1 : Math.max(0.35, 1 - days / 14 * 0.65);
}
