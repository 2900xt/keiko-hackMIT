"use client";
import { useMemo } from "react";
import { DAY, median, type Detection } from "@/lib/detections";
import type { usePlayer } from "@/lib/hooks";
import DetectionsChart from "./DetectionsChart";
import DetectionRow from "./DetectionRow";
import DetectionDetail from "./DetectionDetail";

export type Filter = "all" | "live" | "archive";
export type SortKey = "ts" | "confidence";
export type Player = ReturnType<typeof usePlayer>;
export interface ArchiveState { status: "loading" | "ok" | "error"; note: string | null }

interface Props {
  active: boolean; now: number | null;
  detections: Detection[]; archive: ArchiveState; onRetry: () => void;
  buoy: { lat: number; lon: number };
  filter: Filter; onFilter: (f: Filter) => void;
  sortKey: SortKey; sortDir: 1 | -1; onSort: (k: SortKey) => void;
  onHover: (id: string | null) => void;
  player: Player;
  selectedId: string | null; onSelect: (id: string | null) => void; onShowOnMap: (id: string) => void;
}

const FILTERS: [Filter, string][] = [["all", "All"], ["live", "Live this session"], ["archive", "Archived"]];
// On the Charles the rows are boats, not whales, so the title drops the word when a non-whale class is listed.
const WHALE_WORDS = /whale|dolphin|porpoise|orca|unknown/i;

export default function DatabaseView({ active, now, detections, archive, onRetry, buoy, filter, onFilter, sortKey, sortDir, onSort, onHover, player, selectedId, onSelect, onShowOnMap }: Props) {
  const rows = useMemo(
    () => detections
      .filter((x) => filter === "all" || (filter === "live") === x.live)
      .sort((a, b) => (sortKey === "ts" ? a.t - b.t : a.confidence - b.confidence) * sortDir),
    [detections, filter, sortKey, sortDir],
  );
  const archived = detections.filter((x) => !x.live).length, live = detections.length - archived;
  const conf = median(detections.map((x) => x.confidence));
  const buoys = new Set(detections.map((x) => x.buoy_id)).size || 1;
  const arrow = (k: SortKey) => (k === sortKey ? (sortDir < 0 ? "↓" : "↑") : "");
  const sortState = (k: SortKey) => (k === sortKey ? (sortDir < 0 ? "descending" : "ascending") : undefined);

  const summary =
    archive.status === "loading" ? "Loading the archive…"
    : archive.status === "error" ? archive.note
    : archive.note ?? archived + " archived · " + (live ? live + " new this session, not yet archived" : "none new this session");
  const filterLabel = FILTERS.find(([k]) => k === filter)?.[1].toLowerCase();
  const selectedIndex = selectedId ? rows.findIndex((x) => x.id === selectedId) : -1;

  return (
    <main className={"db view" + (active ? "" : " hidden")} id="view-db" tabIndex={-1} aria-label="Database">
      <div className="db-head">
        <div>
          <div className="eyebrow">Detection database</div>
          <h1 className="db-title"><span>{detections.length}</span> {detections.some((d) => d.species && !WHALE_WORDS.test(d.species)) ? "detections" : "whale detections"}</h1>
          <p className="meta" role="status">{summary}</p>
        </div>
        <div className="db-links">
          <a className="btn" href="../data/detections.csv" download>Download CSV</a>
          <a className="btn btn-quiet" href="https://github.com/2900xt/keiko-hackMIT/tree/main/site/data" rel="noopener">Database on GitHub</a>
        </div>
      </div>

      <dl className="summary" aria-label="Summary">
        <div className="tile"><dt className="eyebrow">Last 24 h</dt><dd className="num">{now ? detections.filter((x) => now - x.t < DAY).length : 0}</dd></div>
        <div className="tile"><dt className="eyebrow">Last 7 days</dt><dd className="num">{now ? detections.filter((x) => now - x.t < 7 * DAY).length : 0}</dd></div>
        <div className="tile"><dt className="eyebrow">Median confidence</dt><dd className="num">{conf === null ? "—" : Math.round(conf * 100) + "%"}</dd></div>
        <div className="tile"><dt className="eyebrow">Buoys reporting</dt><dd className="num">{buoys}</dd></div>
      </dl>

      <section className="chart-block" aria-label="Detections per day">
        <div className="block-head">
          <div className="eyebrow">Detections per day</div>
          <div className="eyebrow eyebrow-quiet">last 14 days, all sources</div>
        </div>
        <DetectionsChart detections={detections} now={now} />
      </section>

      <div className="table-tools">
        <div className="chips" role="group" aria-label="Filter">
          {FILTERS.map(([k, label]) => (
            <button key={k} className="chip" type="button" aria-pressed={filter === k} onClick={() => onFilter(k)}>{label}</button>
          ))}
        </div>
        {filter !== "all" && <div className="meta" role="status">{rows.length} of {detections.length} shown</div>}
      </div>

      <div className="table-scroll">
        <table className="db-table">
          <thead>
            <tr>
              <th scope="col" aria-sort={sortState("ts")}><button className="sort" type="button" onClick={() => onSort("ts")}>Local time <span className="arrow" aria-hidden="true">{arrow("ts")}</span></button></th>
              <th scope="col">Location</th>
              <th scope="col" aria-sort={sortState("confidence")}><button className="sort" type="button" onClick={() => onSort("confidence")}>Confidence <span className="arrow" aria-hidden="true">{arrow("confidence")}</span></button></th>
              <th scope="col">Spectrogram</th>
              <th scope="col">Audio</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((d) => <DetectionRow key={d.id} d={d} origin={buoy} onHover={onHover} onSelect={onSelect} player={player} />)}
          </tbody>
        </table>
      </div>

      {archive.status === "error" && (
        <div className="db-state error" role="alert">
          <span>{archive.note}</span>
          <button type="button" className="btn btn-quiet btn-sm" onClick={onRetry}>Try again</button>
        </div>
      )}
      {rows.length === 0 && archive.status === "loading" && <p className="db-state" role="status">Loading the archive…</p>}
      {rows.length === 0 && archive.status === "ok" && filter !== "all" && (
        <div className="db-state">
          <span>No detections {filterLabel}.</span>
          <button type="button" className="btn btn-quiet btn-sm" onClick={() => onFilter("all")}>Show all</button>
        </div>
      )}
      {rows.length === 0 && archive.status === "ok" && filter === "all" && (
        <p className="db-state">No detections yet. New calls appear here as the buoy hears them.</p>
      )}

      {selectedIndex >= 0 && (
        <DetectionDetail
          d={rows[selectedIndex]} origin={buoy} player={player}
          index={selectedIndex} count={rows.length}
          onStep={(k) => { const r = rows[selectedIndex + k]; if (r) onSelect(r.id); }}
          onClose={() => onSelect(null)} onShowOnMap={onShowOnMap}
        />
      )}
    </main>
  );
}
