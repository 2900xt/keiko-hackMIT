"use client";
import { memo, useEffect, useMemo, useRef } from "react";
import type { Detection } from "@/lib/detections";
import { drawThumb, wavUrl } from "@/lib/dsp";
import type { Player } from "./DatabaseView";

interface Props { d: Detection; onHover: (id: string | null) => void; player: Player }

const DetectionRow = memo(function DetectionRow({ d, onHover, player }: Props) {
  const when = new Date(d.t);
  return (
    <tr className={d.live ? "new" : undefined} onMouseEnter={() => onHover(d.id)} onMouseLeave={() => onHover(null)}>
      <td>
        {when.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" })}
        {d.live ? <span className="tag tag-live">live</span> : <span className="tag tag-archive">{d.source || "archive"}</span>}
        <span className="sub">{when.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}</span>
      </td>
      <td>
        {d.lat.toFixed(5)}, {d.lon.toFixed(5)}
        <span className="sub">{Math.round(d.f0)} Hz · {d.duration_s} s</span>
      </td>
      <td>
        <span className="conf">
          <span className="conf-bar"><i style={{ width: Math.round(d.confidence * 100) + "%" }} /></span>
          {Math.round(d.confidence * 100)}%
        </span>
      </td>
      <td>
        {d.spectrogram
          ? <img className="thumb" src={d.spectrogram} alt="spectrogram" loading="lazy" width={144} height={48} />
          : <Thumb d={d} />}
      </td>
      <td><PlayButton d={d} player={player} /></td>
    </tr>
  );
});
export default DetectionRow;

// Spectrogram of a live call, drawn from its parameters.
function Thumb({ d }: { d: Detection }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => { if (ref.current) drawThumb(ref.current, d); }, [d]);
  return <canvas ref={ref} className="thumb" width={144} height={48} />;
}

const ICON_PLAY = <svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>;
const ICON_STOP = <svg viewBox="0 0 24 24"><path d="M6 6h12v12H6z" /></svg>;

function PlayButton({ d, player }: { d: Detection; player: Player }) {
  // archived rows ship a clip URL; live rows synthesise an 8 kHz WAV from the call
  const src = useMemo(() => d.clip ?? wavUrl(d), [d]);
  useEffect(() => () => { if (!d.clip) URL.revokeObjectURL(src); }, [d.clip, src]);
  const playing = player.playing === src;
  return (
    <button
      type="button" className={"play" + (playing ? " playing" : "")}
      aria-label={"Play clip, " + d.duration_s.toFixed(1) + " seconds"}
      onClick={() => player.toggle(src)}
    >
      <span className="ic">{playing ? ICON_STOP : ICON_PLAY}</span>
      <span>{d.duration_s.toFixed(1)} s</span>
    </button>
  );
}
