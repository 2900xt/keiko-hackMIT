"use client";
import { memo, useEffect, useMemo, useRef } from "react";
import { offsetFrom, type Detection } from "@/lib/detections";
import { drawThumb, wavUrl } from "@/lib/dsp";
import type { Player } from "./DatabaseView";

interface Props { d: Detection; origin: { lat: number; lon: number }; onHover: (id: string | null) => void; onSelect: (id: string) => void; player: Player }

const DetectionRow = memo(function DetectionRow({ d, origin, onHover, onSelect, player }: Props) {
  const when = new Date(d.t);
  const describe = "Spectrogram of a " + Math.round(d.f0) + " Hz call, " + d.duration_s + " seconds";
  const dateStr = when.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  // Hover or keyboard focus on a row highlights its dot on the map. A click
  // anywhere on the row (except its own buttons) opens the detail overlay; the
  // time is a real button so the keyboard path is the same.
  const open = (e: React.MouseEvent) => { if (!(e.target as HTMLElement).closest("button, a")) onSelect(d.id); };
  return (
    <tr className={"row" + (d.live ? " new" : "")} data-id={d.id} onClick={open} onMouseEnter={() => onHover(d.id)} onMouseLeave={() => onHover(null)} onFocus={() => onHover(d.id)} onBlur={() => onHover(null)}>
      <td>
        <button type="button" className="rowbtn" onClick={() => onSelect(d.id)} aria-label={"Open detection, " + when.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) + " " + dateStr}>
          {when.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" })}
        </button>
        {d.live ? <span className="tag tag-live">live</span> : <span className="tag tag-archive">{d.source || "archive"}</span>}
        <span className="sub">{dateStr}</span>
      </td>
      <td>
        {d.lat.toFixed(5)}, {d.lon.toFixed(5)}
        <span className="sub">{offsetFrom(origin, d)} · {Math.round(d.f0)} Hz · {d.duration_s} s</span>
      </td>
      <td>
        <span className="conf">
          <span className="conf-bar" aria-hidden="true"><i style={{ width: Math.round(d.confidence * 100) + "%" }} /></span>
          {Math.round(d.confidence * 100)}%
        </span>
      </td>
      <td>
        {d.spectrogram
          ? <img className="thumb" src={d.spectrogram} alt={describe} loading="lazy" width={144} height={48} />
          : <Thumb d={d} label={describe} />}
      </td>
      <td><PlayButton d={d} player={player} /></td>
    </tr>
  );
});
export default DetectionRow;

// Spectrogram of a live call, drawn from its parameters.
function Thumb({ d, label }: { d: Detection; label: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => { if (ref.current) drawThumb(ref.current, d); }, [d]);
  return <canvas ref={ref} className="thumb" width={144} height={48} role="img" aria-label={label} />;
}

const ICON_PLAY = <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7z" /></svg>;
const ICON_STOP = <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6h12v12H6z" /></svg>;

function PlayButton({ d, player }: { d: Detection; player: Player }) {
  // archived rows ship a clip URL; live rows synthesise an 8 kHz WAV from the call
  const src = useMemo(() => d.clip ?? wavUrl(d), [d]);
  useEffect(() => () => { if (!d.clip) URL.revokeObjectURL(src); }, [d.clip, src]);
  const playing = player.playing === src;
  const failed = player.failed !== null && player.failed.endsWith(src.replace(/^\.?\/?/, ""));
  const secs = d.duration_s.toFixed(1);
  return (
    <button
      type="button" className={"play" + (playing ? " playing" : "")}
      aria-pressed={playing}
      aria-label={(playing ? "Stop" : "Play") + " " + secs + " second clip"}
      title={failed ? "This clip didn't load. Try again." : undefined}
      onClick={() => player.toggle(src)}
    >
      <span className="ic">{playing ? ICON_STOP : ICON_PLAY}</span>
      <span>{failed ? "retry" : secs + " s"}</span>
    </button>
  );
}
