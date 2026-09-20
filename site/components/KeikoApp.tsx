"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createFeed, type Buoy, type Hearing, type Status, type Telemetry, type Track } from "@/lib/feed";
import { fromArchive, fromLive, loadArchive, loadBuoy, type BuoyInfo, type Detection } from "@/lib/detections";
import { DEFAULT_SITE, distanceM, readSiteKey, rememberSiteKey, SITE_RADIUS_M, SITES, storeSiteKey, type SiteKey } from "@/lib/sites";
import { useFeedEvent, useNow, usePlayer } from "@/lib/hooks";
import Header from "./Header";
import LiveView from "./LiveView";
import DatabaseView, { type ArchiveState, type Filter, type SortKey } from "./DatabaseView";
import Ask from "./Ask";

export type View = "live" | "db";
export type Link = "" | "on" | "stale" | "off"; // connection state, doubles as a CSS class

export default function KeikoApp() {
  // ---------- site (?site=charles | harbor) ----------
  // The build renders the default site; the browser's choice is read once mounted, so both renders agree.
  const [siteKey, setSiteKey] = useState<SiteKey>(DEFAULT_SITE);
  useEffect(() => { const k = readSiteKey(); storeSiteKey(k); if (k !== DEFAULT_SITE) { setSiteKey(k); setBuoys([SITES[k].buoy]); } }, []);
  const site = SITES[siteKey];
  const feed = useMemo(() => createFeed(site), [site]);
  const now = useNow(1000);

  // ---------- view (hash-routed: #live / #db) ----------
  const [view, setView] = useState<View>("live");
  useEffect(() => {
    const sync = () => setView(location.hash === "#db" ? "db" : "live");
    sync();
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);
  // Next writes its metadata <title> after hydration, so the per-view title is
  // re-applied on every clock tick rather than once on mount.
  useEffect(() => { document.title = (view === "db" ? "Database" : "Live") + " · Keiko"; }, [view, now]);
  const skipToContent = useCallback(() => {
    document.getElementById(view === "db" ? "view-db" : "view-live")?.focus();
  }, [view]);

  // ---------- buoys ----------
  const [buoys, setBuoys] = useState<Buoy[]>([feed.buoy]);
  const [status, setStatus] = useState<Status>({ connected: false, node_online: false, synthetic: feed.synthetic });
  const [telemetry, setTelemetry] = useState<Telemetry | null>(null);   // the physical buoy's
  const [lastAt, setLastAt] = useState(0);
  const [buoyInfo, setBuoyInfo] = useState<BuoyInfo | null | undefined>(undefined); // undefined = loading
  useFeedEvent(feed, "buoys", setBuoys);
  useFeedEvent(feed, "status", setStatus);
  useFeedEvent(feed, "telemetry", (t) => { if (t.id === feed.buoy.id) { setTelemetry(t); setLastAt(Date.now()); } });
  const [hearing, setHearing] = useState<Hearing | null>(null);
  useFeedEvent(feed, "window", setHearing);
  const [tracks, setTracks] = useState<Track[]>([]);
  useFeedEvent(feed, "track", (t) => setTracks((xs) => [...xs.filter((x) => x.id !== t.id), t]));
  useEffect(() => {
    let alive = true;
    loadBuoy(feed.buoy.id).then((b) => alive && setBuoyInfo(b)).catch(() => alive && setBuoyInfo(null));
    return () => { alive = false; };
  }, [feed]);
  // Moving the demo to the other site: the old feed's telemetry, calls and tracks are 10 km away, so they go.
  const changeSite = useCallback((k: SiteKey) => {
    if (k === siteKey) return;
    rememberSiteKey(k);
    setSiteKey(k);
    setBuoys([SITES[k].buoy]); setTelemetry(null); setLastAt(0); setHearing(null); setTracks([]);
    setStatus({ connected: false, node_online: false, synthetic: true });
    setDetections((xs) => xs.filter((x) => !x.live));
  }, [siteKey]);

  const age = now && lastAt ? now - lastAt : 0;
  const link: Link = !lastAt ? "" : age > 10000 ? "off" : age > 5000 ? "stale" : "on";
  const linkWord = !lastAt ? "connecting" : link === "off" ? "offline" : link === "stale" ? "stale" : "online";

  // ---------- detections ----------
  const [detections, setDetections] = useState<Detection[]>([]);
  const [archive, setArchive] = useState<ArchiveState>({ status: "loading", note: null });
  const gen = useRef(0); // ignore responses from a superseded load
  const loadDb = useCallback(() => {
    const g = ++gen.current;
    setArchive({ status: "loading", note: null });
    loadArchive()
      .then((db) => {
        if (g !== gen.current) return;
        const rows = db.detections.slice().sort((a, b) => a.timestamp_utc.localeCompare(b.timestamp_utc)).map(fromArchive);
        setDetections((xs) => [...rows, ...xs.filter((x) => x.live)]);
        setArchive({ status: "ok", note: db.detections.length ? null : "The archive is empty." });
      })
      .catch((e: Error) => {
        if (g !== gen.current) return;
        const why = /^\d{3}$/.test(e.message) ? "the server answered " + e.message : "network error";
        setArchive({ status: "error", note: "Couldn't load the archive (" + why + "). Only calls heard this session are listed." });
      });
  }, []);
  useEffect(() => { loadDb(); return () => { gen.current++; }; }, [loadDb]);

  // New calls are announced to screen readers; sighted users see the row flash.
  const [announce, setAnnounce] = useState("");
  useFeedEvent(feed, "detection", (d) => {
    setDetections((xs) => xs.some((x) => x.id === d.id) ? xs : [...xs, fromLive(d, feed.buoy.id, true)]);
    setAnnounce("New detection, " + Math.round(d.confidence * 100) + "% confidence, " + new Date(d.ts).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }));
  });

  useEffect(() => { feed.start(); return () => feed.stop(); }, [feed]);

  // The archive holds every site's rows; this page shows the ones near its buoy (live rows are already its own).
  const shown = useMemo(() => detections.filter((d) => d.live || distanceM(feed.buoy, d) <= SITE_RADIUS_M), [detections, feed.buoy]);

  // ---------- table state ----------
  const [filter, setFilter] = useState<Filter>("all");
  const [sortKey, setSortKey] = useState<SortKey>("ts");
  const [sortDir, setSortDir] = useState<1 | -1>(-1);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null); // row open in the detail overlay
  const [focus, setFocus] = useState<{ id: string; n: number } | null>(null);
  const showOnMap = useCallback((id: string) => {
    setSelectedId(null);
    setFocus((f) => ({ id, n: (f?.n ?? 0) + 1 }));
    setHoveredId(id);
    location.hash = "live";
  }, []);
  const player = usePlayer();

  const position = telemetry ? { lat: telemetry.lat, lon: telemetry.lon } : { lat: feed.buoy.lat, lon: feed.buoy.lon };

  return (
    <>
      <Header view={view} count={shown.length} link={link} linkWord={linkWord} now={now} onSkip={skipToContent} />
      <p className="sr-only" role="status" aria-live="polite">{announce}</p>
      <LiveView
        feed={feed} active={view === "live"} now={now}
        buoyId={telemetry?.id ?? "—"} position={position} telemetry={telemetry} buoyInfo={buoyInfo}
        link={link} linkWord={linkWord} age={age} lastAt={lastAt}
        detections={shown} hoveredId={hoveredId} focus={focus}
        buoys={buoys} tracks={tracks} hearing={hearing} status={status}
        site={site} onSite={changeSite}
      />
      <DatabaseView
        active={view === "db"} now={now} detections={shown} archive={archive} onRetry={loadDb}
        buoy={feed.buoy}
        filter={filter} onFilter={setFilter}
        sortKey={sortKey} sortDir={sortDir}
        onSort={(k) => { if (k === sortKey) setSortDir((d) => (d === 1 ? -1 : 1)); else { setSortKey(k); setSortDir(-1); } }}
        onHover={setHoveredId} player={player}
        selectedId={selectedId} onSelect={setSelectedId} onShowOnMap={showOnMap}
      />
      <Ask />
    </>
  );
}
