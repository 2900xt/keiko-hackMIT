"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { createFeed, type Telemetry } from "@/lib/feed";
import { fromArchive, fromLive, loadArchive, loadBuoy, type BuoyInfo, type Detection } from "@/lib/detections";
import { useFeedEvent, useNow, usePlayer } from "@/lib/hooks";
import Header from "./Header";
import LiveView from "./LiveView";
import DatabaseView, { type Filter, type SortKey } from "./DatabaseView";

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
  const [archiveNote, setArchiveNote] = useState<string | null>("Loading archive…");
  const add = useCallback((d: Detection) => setDetections((xs) => [...xs, d]), []);
  useEffect(() => {
    let alive = true;
    loadArchive()
      .then((db) => {
        if (!alive) return;
        const rows = db.detections.slice().sort((a, b) => a.timestamp_utc.localeCompare(b.timestamp_utc)).map(fromArchive);
        setDetections((xs) => [...rows, ...xs]);
        setArchiveNote(db.detections.length ? null : "Archive is empty");
      })
      .catch((e: Error) => {
        if (!alive) return;
        setArchiveNote("Archive unavailable (" + e.message + "); showing synthetic rows only");
        setDetections((xs) => [...feed.backfill(8).map((d) => fromLive(d, feed.buoy.id, false)), ...xs]);
      });
    return () => { alive = false; };
  }, [feed]);
  useFeedEvent(feed, "detection", (d) => add(fromLive(d, feed.buoy.id, true)));

  useEffect(() => { feed.start(); return () => feed.stop(); }, [feed]);

  // ---------- table state ----------
  const [filter, setFilter] = useState<Filter>("all");
  const [sortKey, setSortKey] = useState<SortKey>("ts");
  const [sortDir, setSortDir] = useState<1 | -1>(-1);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const player = usePlayer();

  const position = telemetry ? { lat: telemetry.lat, lon: telemetry.lon } : { lat: feed.buoy.lat, lon: feed.buoy.lon };

  return (
    <>
      <Header view={view} count={detections.length} link={link} linkWord={linkWord} now={now} />
      <LiveView
        feed={feed} active={view === "live"} now={now}
        buoyId={telemetry?.id ?? "—"} position={position} telemetry={telemetry} buoyInfo={buoyInfo}
        link={link} linkWord={linkWord} age={age} lastAt={lastAt}
        detections={detections} hoveredId={hoveredId}
      />
      <DatabaseView
        active={view === "db"} now={now} detections={detections} archiveNote={archiveNote}
        filter={filter} onFilter={setFilter}
        sortKey={sortKey} sortDir={sortDir}
        onSort={(k) => { if (k === sortKey) setSortDir((d) => (d === 1 ? -1 : 1)); else { setSortKey(k); setSortDir(-1); } }}
        onHover={setHoveredId} player={player}
      />
    </>
  );
}
