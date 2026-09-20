"use client";
import dynamic from "next/dynamic";
import type { Feed, Telemetry } from "@/lib/feed";
import { ago, agoParts, RANGE_M, type BuoyInfo, type Detection } from "@/lib/detections";
import Spectrogram from "./Spectrogram";
import Waveform from "./Waveform";
import type { Link } from "./KeikoApp";

// Leaflet touches window at import time, so the map only renders on the client.
const MapView = dynamic(() => import("./MapView"), { ssr: false });

interface Props {
  feed: Feed; active: boolean; now: number | null;
  buoyId: string; position: { lat: number; lon: number }; telemetry: Telemetry | null;
  buoyInfo: BuoyInfo | null | undefined;
  link: Link; linkWord: string; age: number; lastAt: number;
  detections: Detection[]; hoveredId: string | null; focus: { id: string; n: number } | null;
}

export default function LiveView({ feed, active, now, buoyId, position, telemetry, buoyInfo, link, linkWord, age, lastAt, detections, hoveredId, focus }: Props) {
  return (
    <main className={"grid view" + (active ? "" : " hidden")} id="view-live" tabIndex={-1} aria-label="Live">
      <section className="map-cell" aria-label="Map">
        <MapView buoyId={feed.buoy.id} position={position} detections={detections} hoveredId={hoveredId} focus={focus} active={active} now={now} />
        <div className="map-key" aria-label="Map key">
          <span><i className="key-buoy" aria-hidden="true" />Buoy</span>
          <span><i className="key-range" aria-hidden="true" />Hydrophone range, {RANGE_M} m</span>
          <span><i className="key-sight" aria-hidden="true" />Detection, fades with age</span>
        </div>
      </section>

      <aside className="rail">
        <section className="block" aria-label="Buoy">
          <div className="block-head">
            <div className="eyebrow">Buoy</div>
            <div className="eyebrow eyebrow-quiet">{lastAt ? "updated " + ago(age) : "—"}</div>
          </div>
          <div className="buoy-id">
            <span>{buoyId}</span>
            <span className={"state " + link}>{linkWord}</span>
          </div>
          {feed.synthetic && (
            <p className="notice">
              <b>Simulated feed.</b>
              <span>Telemetry, audio and calls are generated in the browser, not recorded on the river.</span>
            </p>
          )}
          <dl className="kv">
            <div>
              <dt className="eyebrow">Position</dt>
              <dd className="pos">
                <span>{telemetry ? telemetry.lat.toFixed(5) : "—"}</span>
                <span className="sep" aria-hidden="true">,</span>
                <span>{telemetry ? telemetry.lon.toFixed(5) : "—"}</span>
              </dd>
            </div>
            <div>
              <dt className="eyebrow">Hydrophone</dt>
              <dd className="val">{buoyInfo ? buoyInfo.hydrophone + " · " + buoyInfo.sample_rate_hz / 1000 + " kHz" : "—"}</dd>
            </div>
            <div>
              <dt className="eyebrow">Deployed</dt>
              <dd className="val">
                {buoyInfo ? new Date(buoyInfo.deployed_utc).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" }) : "—"}
              </dd>
            </div>
          </dl>
        </section>

        <Stats now={now} detections={detections} />
      </aside>

      <section className="sound" aria-label="Hydrophone audio">
        <div className="panel">
          <div className="block-head">
            <div className="eyebrow">Waveform</div>
            <div className="eyebrow eyebrow-quiet">Raw signal · 2 kHz · last 128 ms</div>
          </div>
          <Waveform feed={feed} />
        </div>
        <div className="panel">
          <div className="block-head">
            <div className="eyebrow">Spectrogram</div>
            <div className="eyebrow eyebrow-quiet">Mel scale · 0–1 kHz · last 30 s</div>
          </div>
          <Spectrogram feed={feed} />
        </div>
      </section>
    </main>
  );
}

function Stats({ now, detections }: { now: number | null; detections: Detection[] }) {
  const latest = detections.length ? Math.max(...detections.map((x) => x.t)) : 0;
  const last = now && latest ? agoParts(now - latest) : null;
  let today = 0;
  if (now) { const midnight = new Date(now); midnight.setHours(0, 0, 0, 0); today = detections.filter((x) => x.t >= midnight.getTime()).length; }
  return (
    <dl className="block stats" aria-label="Summary">
      <div className="stat"><dt className="eyebrow">Today</dt><dd className="num">{today}</dd><dd className="unit">{today === 1 ? "detection" : "detections"}</dd></div>
      <div className="stat"><dt className="eyebrow">Last call</dt><dd className="num">{last ? last[0] : "—"}</dd><dd className="unit">{last ? last[1] : "none yet"}</dd></div>
    </dl>
  );
}
