"use client";
import dynamic from "next/dynamic";
import type { Buoy, Feed, Hearing, Status, Telemetry, Track } from "@/lib/feed";
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
  buoys: Buoy[]; tracks: Track[]; hearing: Hearing | null; status: Status;
}

export default function LiveView({ feed, active, now, buoyId, position, telemetry, buoyInfo, link, linkWord, age, lastAt, detections, hoveredId, focus, buoys, tracks, hearing, status }: Props) {
  const simulated = buoys.filter((b) => b.simulated);
  const latest = detections.filter((d) => d.live && d.fix).at(-1);
  return (
    <main className={"grid view" + (active ? "" : " hidden")} id="view-live" tabIndex={-1} aria-label="Live">
      <section className="map-cell" aria-label="Map">
        <MapView buoyId={feed.buoy.id} position={position} detections={detections} hoveredId={hoveredId} focus={focus} active={active} now={now} buoys={buoys} tracks={tracks} />
        <div className="map-key" aria-label="Map key">
          <span><i className="key-buoy" aria-hidden="true" />Buoy</span>
          {simulated.length > 0 && <span><i className="key-buoy-sim" aria-hidden="true" />Simulated buoy</span>}
          <span><i className="key-range" aria-hidden="true" />Hydrophone range, {RANGE_M} m</span>
          <span><i className="key-sight" aria-hidden="true" />Detection, fades with age</span>
          {tracks.length > 0 && <span><i className="key-track" aria-hidden="true" />Track</span>}
        </div>

        <section className="sound" aria-label="Hydrophone audio">
          <div className="panel">
            <div className="block-head">
              <div className="eyebrow">Waveform</div>
              <div className="eyebrow eyebrow-quiet">2 kHz · last 128 ms</div>
            </div>
            <Waveform feed={feed} />
          </div>
          <div className="panel">
            <div className="block-head">
              <div className="eyebrow">Spectrogram</div>
              <div className="eyebrow eyebrow-quiet">0–1 kHz · last 30 s</div>
            </div>
            <Spectrogram feed={feed} />
          </div>
        </section>
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
          {status.synthetic ? (
            <p className="notice">
              <b>Simulated feed.</b>
              <span>Telemetry, audio and calls are generated in the browser, not recorded at sea.</span>
            </p>
          ) : !status.node_online && (
            <p className="notice">
              <b>{status.connected ? "Buoy offline." : "Server offline."}</b>
              <span>{status.connected ? "The server is up but no pipeline is streaming to it." : "Waiting for the central server."}</span>
            </p>
          )}
          <div className="hearing" aria-live="polite">
            <span className="eyebrow">Hearing now</span>
            <span className={"val" + (hearing?.whale ? " whale" : "")}>
              {hearing ? (hearing.whale ? (hearing.species ?? hearing.label) + " · " + Math.round(hearing.conf * 100) + "%" : "no whale") : "—"}
            </span>
          </div>
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

        <section className="block" aria-label="Localization">
          <div className="block-head">
            <div className="eyebrow">Localization</div>
            <div className="eyebrow eyebrow-quiet">TDOA · {buoys.length} buoys{simulated.length ? " · " + simulated.length + " simulated" : ""}</div>
          </div>
          {latest?.fix ? (
            <>
              <div className="fix">
                <span className="pos"><span>{latest.fix.lat.toFixed(5)}</span><span className="sep" aria-hidden="true">,</span><span>{latest.fix.lon.toFixed(5)}</span></span>
                <span className="err">± {Math.round(latest.fix.err_m)} m</span>
              </div>
              <table className="arrivals">
                <thead><tr><th>Buoy</th><th>Δt</th><th>Range</th></tr></thead>
                <tbody>
                  {latest.fix.arrivals.map((a) => (
                    <tr key={a.buoy_id} className={a.simulated ? "sim" : ""}>
                      <td>{a.buoy_id}{a.simulated && <span className="tag tag-sim">sim</span>}</td>
                      <td>{a.dt_ms >= 0 ? "+" : ""}{a.dt_ms.toFixed(1)} ms</td>
                      <td>{Math.round(a.range_m)} m</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {simulated.length > 0 && (
                <p className="fine">Arrival times at {simulated.map((b) => b.id).join(" and ")} are generated by the server; the fix is a real hyperbolic solve at {latest.fix.c_m_s} m/s.</p>
              )}
            </>
          ) : (
            <p className="fine">{status.synthetic ? "No server: calls are placed at random, not localized." : "Waiting for a call to localize."}</p>
          )}
        </section>

        <Stats now={now} detections={detections} />
      </aside>
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
