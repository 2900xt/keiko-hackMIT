"use client";
import dynamic from "next/dynamic";
import type { Feed, Telemetry } from "@/lib/feed";
import { ago, agoParts, type BuoyInfo, type Detection } from "@/lib/detections";
import { useAudioLevel } from "@/lib/hooks";
import Spectrogram from "./Spectrogram";
import type { Link } from "./KeikoApp";

// Leaflet touches window at import time, so the map only renders on the client.
const MapView = dynamic(() => import("./MapView"), { ssr: false });

interface Props {
  feed: Feed; active: boolean; now: number | null;
  buoyId: string; position: { lat: number; lon: number }; telemetry: Telemetry | null;
  buoyInfo: BuoyInfo | null | undefined;
  link: Link; linkWord: string; age: number; lastAt: number;
  detections: Detection[]; hoveredId: string | null;
}

export default function LiveView({ feed, active, now, buoyId, position, telemetry, buoyInfo, link, linkWord, age, lastAt, detections, hoveredId }: Props) {
  return (
    <main className={"grid view" + (active ? "" : " hidden")} id="view-live">
      <section className="map-cell" aria-label="Map">
        <MapView buoyId={feed.buoy.id} position={position} detections={detections} hoveredId={hoveredId} active={active} now={now} />
        <div className="map-key">
          <span><i className="key-buoy" />Buoy</span>
          <span><i className="key-range" />Hydrophone range</span>
          <span><i className="key-sight" />Detection, fades with age</span>
        </div>
      </section>

      <aside className="rail">
        <section className="block">
          <div className="block-head">
            <div className="eyebrow">Buoy</div>
            <div className="eyebrow eyebrow-quiet">{lastAt ? "updated " + ago(age) : "—"}</div>
          </div>
          <div className="buoy-id">
            <span>{buoyId}</span>
            <span className={"state " + link}>{linkWord}</span>
          </div>
          <div className="kv">
            <div>
              <div className="eyebrow">Position</div>
              <div className="pos">
                <span>{telemetry ? telemetry.lat.toFixed(5) : "—"}</span>
                <span className="sep">,</span>
                <span>{telemetry ? telemetry.lon.toFixed(5) : "—"}</span>
              </div>
            </div>
            <div>
              <div className="eyebrow">Hydrophone</div>
              <div className="val">{buoyInfo ? buoyInfo.hydrophone + " · " + buoyInfo.sample_rate_hz / 1000 + " kHz" : "—"}</div>
            </div>
            <div>
              <div className="eyebrow">Deployed</div>
              <div className="val">
                {buoyInfo ? new Date(buoyInfo.deployed_utc).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" }) : "—"}
              </div>
            </div>
          </div>
        </section>

        <Stats feed={feed} now={now} detections={detections} />

        <section className="block block-grow">
          <div className="block-head">
            <div className="eyebrow">Hydrophone</div>
            <div className="eyebrow eyebrow-quiet">Mel spectrogram · 0–1 kHz · last 30 s</div>
          </div>
          <Spectrogram feed={feed} />
        </section>
      </aside>
    </main>
  );
}

function Stats({ feed, now, detections }: { feed: Feed; now: number | null; detections: Detection[] }) {
  const level = useAudioLevel(feed);
  const latest = detections.length ? Math.max(...detections.map((x) => x.t)) : 0;
  const last = now && latest ? agoParts(now - latest) : null;
  let today = 0;
  if (now) { const midnight = new Date(now); midnight.setHours(0, 0, 0, 0); today = detections.filter((x) => x.t >= midnight.getTime()).length; }
  return (
    <section className="block stats" aria-label="Summary">
      <div className="stat"><div className="eyebrow">Today</div><div className="num">{today}</div><div className="unit">detections</div></div>
      <div className="stat"><div className="eyebrow">Last call</div><div className="num">{last ? last[0] : "—"}</div><div className="unit">{last ? last[1] : " "}</div></div>
      <div className="stat"><div className="eyebrow">Level</div><div className="num">{level === null ? "—" : level.toFixed(0)}</div><div className="unit">dB re 1 µPa</div></div>
    </section>
  );
}
