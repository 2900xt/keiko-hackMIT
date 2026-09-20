"use client";
import { useEffect, useRef } from "react";
import type { Feed } from "@/lib/feed";
import { magma, melOf, MEL_MAX, SPEC_BG, yPct } from "@/lib/dsp";
import { useAudioLevel, useFeedEvent } from "@/lib/hooks";

const SW = 600, SH = 240;
const Y_TICKS: [number, string][] = [[1000, "1 kHz"], [500, "500"], [250, "250"], [100, "100"], [0, "0"]];
const GRID_HZ = [500, 250, 100];

// Scrolling mel spectrogram: each audio frame shifts the canvas one pixel left
// and paints its 80 bins down the right edge.
export default function Spectrogram({ feed }: { feed: Feed }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const level = useAudioLevel(feed);

  useEffect(() => {
    const g = canvas.current?.getContext("2d");
    if (g) { g.fillStyle = SPEC_BG; g.fillRect(0, 0, SW, SH); }
  }, []);

  useFeedEvent(feed, "audio", (a) => {
    const c = canvas.current, g = c?.getContext("2d");
    if (!c || !g) return;
    g.drawImage(c, -1, 0);
    const b = a.bins, n = b.length;
    for (let i = 0; i < n; i++) {
      const y0 = SH - melOf((i + 1) / n * 1000) / MEL_MAX * SH, y1 = SH - melOf(i / n * 1000) / MEL_MAX * SH;
      g.fillStyle = magma(b[i]); g.fillRect(SW - 1, y0, 1, Math.ceil(y1 - y0));
    }
  });

  const pct = level === null ? 0 : Math.max(0, Math.min(100, (level + 60) / 60 * 100));
  return (
    <>
      <div className="spec-wrap">
        <div className="spec-y" aria-hidden="true">
          {Y_TICKS.map(([hz, label]) => <span key={hz} style={{ top: yPct(hz) }}>{label}</span>)}
        </div>
        <div className="spec-box">
          <canvas id="spec" ref={canvas} width={SW} height={SH} aria-label="Live spectrogram" />
          <div className="spec-grid" aria-hidden="true">
            {GRID_HZ.map((hz) => <i key={hz} style={{ top: yPct(hz) }} />)}
          </div>
        </div>
      </div>
      <div className="spec-x" aria-hidden="true"><span>−30 s</span><span>−20 s</span><span>−10 s</span><span>now</span></div>
      <div className="level">
        <span className="eyebrow">Level</span>
        <span className="level-bar"><i style={{ width: pct + "%" }} /></span>
        <span className="level-val">{level === null ? "— dB" : level.toFixed(1) + " dB"}</span>
      </div>
    </>
  );
}
