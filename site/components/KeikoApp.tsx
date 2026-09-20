"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createFeed, type Telemetry } from "@/lib/feed";
import { fromArchive, fromLive, loadArchive, loadBuoy, type BuoyInfo, type Detection } from "@/lib/detections";
import { useFeedEvent, useNow, usePlayer } from "@/lib/hooks";
import Header from "./Header";
import LiveView from "./LiveView";
import DatabaseView, { type ArchiveState, type Filter, type SortKey } from "./DatabaseView";

export type View = "live" | "db";
export type Link = "" | "on" | "stale" | "off"; // connection state, doubles as a CSS class

export default function KeikoApp() {
  const feed = useMemo(() => createFeed(), []);
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

  // ---------- buoy ----------
  const [telemetry, setTelemetry] = useState<Telemetry | null>(null);
  const [lastAt, setLastAt] = useState(0);
  const [buoyInfo, setBuoyInfo] = useState<BuoyInfo | null | undefined>(undefined); // undefined = loading
  useFeedEvent(feed, "telemetry", (t) => { setTelemetry(t); setLastAt(Date.now()); });
  useEffect(() => {
    let alive = true;
    loadBuoy(feed.buoy.id).then((b) => alive && setBuoyInfo(b)).catch(() => alive && setBuoyInfo(null));
    return () => { alive = false; };
  }, [feed]);

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
    setDetections((xs) => [...xs, fromLive(d, feed.buoy.id, true)]);
    setAnnounce("New detection, " + Math.round(d.confidence * 100) + "% confidence, " + new Date(d.ts).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }));
  });

  useEffect(() => { feed.start(); return () => feed.stop(); }, [feed]);

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
      <Header view={view} count={detections.length} link={link} linkWord={linkWord} now={now} onSkip={skipToContent} />
      <p className="sr-only" role="status" aria-live="polite">{announce}</p>
      <LiveView
        feed={feed} active={view === "live"} now={now}
        buoyId={telemetry?.id ?? "—"} position={position} telemetry={telemetry} buoyInfo={buoyInfo}
        link={link} linkWord={linkWord} age={age} lastAt={lastAt}
        detections={detections} hoveredId={hoveredId} focus={focus}
      />
      <DatabaseView
        active={view === "db"} now={now} detections={detections} archive={archive} onRetry={loadDb}
        buoy={feed.buoy}
        filter={filter} onFilter={setFilter}
        sortKey={sortKey} sortDir={sortDir}
        onSort={(k) => { if (k === sortKey) setSortDir((d) => (d === 1 ? -1 : 1)); else { setSortKey(k); setSortDir(-1); } }}
        onHover={setHoveredId} player={player}
        selectedId={selectedId} onSelect={setSelectedId} onShowOnMap={showOnMap}
      />
    </>
  );
}
