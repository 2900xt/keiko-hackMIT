"use client";
import { useEffect, useMemo, useRef } from "react";
import { offsetFrom, RANGE_M, type Detection } from "@/lib/detections";
import { drawThumb, wavUrl, yPct } from "@/lib/dsp";
import type { Player } from "./DatabaseView";

interface Props {
  d: Detection; origin: { lat: number; lon: number }; player: Player;
  index: number; count: number;            // position in the current table order
  onStep: (k: -1 | 1) => void;             // previous / next row
  onClose: () => void;
  onShowOnMap: (id: string) => void;
}

const Y_TICKS: [number, string][] = [[1000, "1 kHz"], [500, "500"], [250, "250"], [100, "100"], [0, "0"]];
const GRID_HZ = [500, 250, 100];
const SW = 600, SH = 200;

// One detection, in full: a native <dialog> (Escape closes, focus is trapped
// and returned to the row), the spectrogram at readable size, the clip, and
// every field the row abbreviates. ← → step through the table's current order.
export default function DetectionDetail({ d, origin, player, index, count, onStep, onClose, onShowOnMap }: Props) {
  const dlg = useRef<HTMLDialogElement>(null);
  const current = useRef(d.id);
  current.current = d.id;
  useEffect(() => {
    // The dialog unmounts rather than closing, so focus goes back to the row by
    // hand: to the time button of whichever row is showing when it closes.
    const el = dlg.current;
    if (el && !el.open) el.showModal();
    return () => {
      const row = document.querySelector<HTMLElement>('tr[data-id="' + CSS.escape(current.current) + '"] .rowbtn');
      row?.focus();
    };
  }, []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft") onStep(-1);
      else if (e.key === "ArrowRight") onStep(1);
      else if (e.key === "Escape") { e.preventDefault(); onClose(); }
    };
    const el = dlg.current;
    el?.addEventListener("keydown", onKey);
    return () => el?.removeEventListener("keydown", onKey);
  }, [onStep, onClose]);

  const when = new Date(d.t);
  const src = useMemo(() => d.clip ?? wavUrl(d), [d]);
  useEffect(() => () => { if (!d.clip) URL.revokeObjectURL(src); }, [d.clip, src]);
  const playing = player.playing === src;
  const secs = d.duration_s.toFixed(1);
  const pct = Math.round(d.confidence * 100);
  // Archived PNGs cover the clip exactly; a live call is drawn with half a second of river either side.
  const padded = !d.spectrogram, span = padded ? d.duration_s + 1 : d.duration_s;

  return (
    <dialog ref={dlg} className="detail" onClose={onClose} onCancel={(e) => { e.preventDefault(); onClose(); }} aria-labelledby="detail-title">
      <div className="detail-head">
        <div>
          <div className="eyebrow">Detection {index + 1} of {count}</div>
          <h2 className="detail-title" id="detail-title">
            {when.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" })}
            {d.live ? <span className="tag tag-live">live</span> : <span className="tag tag-archive">{d.source || "archive"}</span>}
          </h2>
          <p className="meta detail-when">
            <span>{when.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric" })}</span>
            <span className="eyebrow-quiet">{d.ts.replace("T", " ").replace(/\.\d+Z$/, "Z").replace(/Z$/, " UTC")}</span>
          </p>
        </div>
        <button type="button" className="close" onClick={onClose} aria-label="Close">
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 3l10 10M13 3L3 13" /></svg>
        </button>
      </div>

      <div className="detail-spec">
        <div className="block-head">
          <div className="eyebrow">Spectrogram</div>
          <div className="eyebrow eyebrow-quiet">Mel scale · 0–1 kHz · {span.toFixed(1)} s window</div>
        </div>
        <div className="spec-wrap">
          <div className="spec-y" aria-hidden="true">
            {Y_TICKS.map(([hz, label]) => <span key={hz} style={{ top: yPct(hz) }}>{label}</span>)}
          </div>
          <div className="spec-box">
            {d.spectrogram
              ? <img className="scope" src={d.spectrogram} alt={"Spectrogram of a " + Math.round(d.f0) + " Hz call, " + secs + " seconds"} style={{ objectFit: "fill" }} />
              : <BigThumb d={d} label={"Spectrogram of a " + Math.round(d.f0) + " Hz call, " + secs + " seconds"} />}
            <div className="spec-grid" aria-hidden="true">
              {GRID_HZ.map((hz) => <i key={hz} style={{ top: yPct(hz) }} />)}
            </div>
          </div>
        </div>
        <div className="spec-x" aria-hidden="true">
          {padded
            ? <><span>−0.5 s</span><span>call starts</span><span>{d.duration_s} s</span><span>+0.5 s</span></>
            : <><span>0 s</span><span>{(d.duration_s / 2).toFixed(1)} s</span><span>{secs} s</span></>}
        </div>
      </div>

      <div className="detail-actions">
        <button type="button" className={"play" + (playing ? " playing" : "")} aria-pressed={playing} onClick={() => player.toggle(src)}>
          <span className="ic">{playing ? ICON_STOP : ICON_PLAY}</span>
          <span>{playing ? "Stop" : "Play clip"} · {secs} s</span>
        </button>
        <a className="btn btn-quiet" href={src} download={d.id + ".wav"}>Download WAV</a>
        <span className="spacer" />
        <button type="button" className="btn btn-quiet" onClick={() => onShowOnMap(d.id)}>Show on map</button>
      </div>

      <dl className="detail-facts">
        <div>
          <dt className="eyebrow">Confidence</dt>
          <dd><span className="conf"><span className="conf-bar" aria-hidden="true"><i style={{ width: pct + "%" }} /></span>{pct}%</span></dd>
        </div>
        <div>
          <dt className="eyebrow">Peak frequency</dt>
          <dd>{Math.round(d.f0)} Hz{d.live && d.sweep ? <span className="sub">{d.sweep > 0 ? "rising" : "falling"} {Math.abs(d.sweep)} Hz over the call</span> : null}</dd>
        </div>
        <div>
          <dt className="eyebrow">Duration</dt>
          <dd>{secs} s</dd>
        </div>
        <div>
          <dt className="eyebrow">Location</dt>
          <dd>{d.lat.toFixed(5)}, {d.lon.toFixed(5)}<span className="sub">{offsetFrom(origin, d)} · within the {RANGE_M} m hydrophone range</span></dd>
        </div>
        <div>
          <dt className="eyebrow">Buoy</dt>
          <dd>{d.buoy_id}</dd>
        </div>
        <div>
          <dt className="eyebrow">Record</dt>
          <dd>{d.id}<span className="sub">{d.live ? "heard this session, not yet in the archive" : (d.source === "synthetic" ? "generated row in " : "field recording in ") + "data/detections.csv"}</span></dd>
        </div>
      </dl>

      <div className="detail-nav">
        <button type="button" className="btn btn-quiet btn-sm" disabled={index === 0} onClick={() => onStep(-1)}>← Previous</button>
        <span className="hint"><kbd>←</kbd> <kbd>→</kbd> to step, <kbd>Esc</kbd> to close</span>
        <button type="button" className="btn btn-quiet btn-sm" disabled={index >= count - 1} onClick={() => onStep(1)}>Next →</button>
      </div>
    </dialog>
  );
}

function BigThumb({ d, label }: { d: Detection; label: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => { if (ref.current) drawThumb(ref.current, d); }, [d]);
  return <canvas ref={ref} className="scope" width={SW} height={SH} role="img" aria-label={label} />;
}

const ICON_PLAY = <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7z" /></svg>;
const ICON_STOP = <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6h12v12H6z" /></svg>;
