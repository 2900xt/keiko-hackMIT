"use client";
import { useMemo } from "react";
import { DAY, median, type Detection } from "@/lib/detections";
import type { usePlayer } from "@/lib/hooks";
import DetectionsChart from "./DetectionsChart";
import DetectionRow from "./DetectionRow";

export type Filter = "all" | "live" | "archive";
export type SortKey = "ts" | "confidence";
export type Player = ReturnType<typeof usePlayer>;

interface Props {
  active: boolean; now: number | null;
  detections: Detection[]; archiveNote: string | null;
  filter: Filter; onFilter: (f: Filter) => void;
  sortKey: SortKey; sortDir: 1 | -1; onSort: (k: SortKey) => void;
  onHover: (id: string | null) => void;
  player: Player;
}

const FILTERS: [Filter, string][] = [["all", "All"], ["live", "Live this session"], ["archive", "Archived"]];

export default function DatabaseView({ active, now, detections, archiveNote, filter, onFilter, sortKey, sortDir, onSort, onHover, player }: Props) {
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

  return (
    <main className={"db view" + (active ? "" : " hidden")} id="view-db">
      <div className="db-head">
        <div>
          <div className="eyebrow">Sightings</div>
          <h1 className="db-title"><span>{detections.length}</span> whale detections</h1>
          <p className="meta">{archiveNote ?? archived + " archived in data/detections.csv · " + live + " live this session, not yet archived"}</p>
        </div>
        <div className="db-links">
          <a className="btn" href="data/detections.csv" download>Download CSV</a>
          <a className="btn btn-quiet" href="https://github.com/2900xt/keiko-hackMIT/tree/main/site/data" rel="noopener">Database on GitHub</a>
        </div>
      </div>

      <section className="summary" aria-label="Summary">
        <div className="tile"><div className="eyebrow">Last 24 h</div><div className="num">{now ? detections.filter((x) => now - x.t < DAY).length : 0}</div></div>
        <div className="tile"><div className="eyebrow">Last 7 days</div><div className="num">{now ? detections.filter((x) => now - x.t < 7 * DAY).length : 0}</div></div>
        <div className="tile"><div className="eyebrow">Median confidence</div><div className="num">{conf === null ? "—" : Math.round(conf * 100) + "%"}</div></div>
        <div className="tile"><div className="eyebrow">Buoys reporting</div><div className="num">{buoys}</div></div>
      </section>

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
            <button key={k} className={"chip" + (filter === k ? " on" : "")} type="button" onClick={() => onFilter(k)}>{label}</button>
          ))}
        </div>
        <div className="meta">{rows.length} of {detections.length} shown</div>
      </div>

      <div className="table-scroll">
        <table className="db-table">
          <thead>
            <tr>
              <th><button className={"sort" + (sortKey === "ts" ? " on" : "")} type="button" onClick={() => onSort("ts")}>Time <span className="arrow">{arrow("ts")}</span></button></th>
              <th>Location</th>
              <th><button className={"sort" + (sortKey === "confidence" ? " on" : "")} type="button" onClick={() => onSort("confidence")}>Confidence <span className="arrow">{arrow("confidence")}</span></button></th>
              <th>Spectrogram</th>
              <th>Audio</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((d) => <DetectionRow key={d.id} d={d} onHover={onHover} player={player} />)}
          </tbody>
        </table>
      </div>
      {rows.length === 0 && <p className="db-empty">No detections match.</p>}
    </main>
  );
}
