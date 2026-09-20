// Demo sites for the simulated data, from data/sites.json (shared with server/keiko_server.py --site and
// tools/keiko_data.py synth --site). The site fixes where the buoy sits, the channel the simulated sources move
// along, and what the water sounds like there: whale-like tonal calls in the harbor, river traffic on the Charles.
import raw from "../data/sites.json";
import type { Buoy } from "./feed";

export type SiteKey = "charles" | "harbor";
export type Soundscape = "whale" | "river";
export interface Site {
  key: SiteKey; name: string; place: string; buoy: Buoy;
  channel: { bearing_deg: number; half_len_m: number; half_width_m: number };
  soundscape: Soundscape; classes: string[];
}

const table = raw.sites as Record<SiteKey, Omit<Site, "key">>;
export const SITE_KEYS = Object.keys(table) as SiteKey[];
export const DEFAULT_SITE = raw.default as SiteKey;
export const SITES: Record<SiteKey, Site> = Object.fromEntries(SITE_KEYS.map((k) => [k, { key: k, ...table[k] }])) as Record<SiteKey, Site>;

export const isSiteKey = (k: unknown): k is SiteKey => typeof k === "string" && k in table;

const STORE = "keiko.site";

// ?site=harbor wins, then the last choice on this browser, then the file's default. Server-safe.
export function readSiteKey(): SiteKey {
  if (typeof window === "undefined") return DEFAULT_SITE;
  const q = new URLSearchParams(window.location.search).get("site");
  if (isSiteKey(q)) return q;
  try { const s = window.localStorage.getItem(STORE); if (isSiteKey(s)) return s; } catch { /* private mode */ }
  return DEFAULT_SITE;
}

export function storeSiteKey(k: SiteKey) {
  try { window.localStorage.setItem(STORE, k); } catch { /* private mode */ }
}

export function rememberSiteKey(k: SiteKey) {
  storeSiteKey(k);
  const url = new URL(window.location.href);
  if (k === DEFAULT_SITE) url.searchParams.delete("site"); else url.searchParams.set("site", k);
  window.history.replaceState(null, "", url);
}

// Metres between two points, flat-earth; enough to tell one site's rows from another's 10 km away.
export function distanceM(a: { lat: number; lon: number }, b: { lat: number; lon: number }) {
  const north = (b.lat - a.lat) * 111320, east = (b.lon - a.lon) * 111320 * Math.cos(a.lat * Math.PI / 180);
  return Math.hypot(north, east);
}
export const SITE_RADIUS_M = 5000; // an archived row belongs to the site whose buoy is within this
