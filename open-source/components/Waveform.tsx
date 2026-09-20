"use client";
import { useEffect, useRef } from "react";
import type { Feed } from "@/lib/feed";
import { SPEC_BG } from "@/lib/dsp";
import { useAudioLevel, useFeedEvent } from "@/lib/hooks";

const WW = 600, WH = 240;
const Y_TICKS: [number, string][] = [[1, "+1"], [0.5, "+0.5"], [0, "0"], [-0.5, "−0.5"], [-1, "−1"]];
const GRID = [0.5, 0, -0.5];
const yPct = (v: number) => (((1 - v) / 2) * 100).toFixed(2) + "%";

// Oscilloscope of the raw hydrophone signal, before the FFT: each audio frame
// (256 samples at 2 kHz, 128 ms) is drawn as one trace over a short afterglow.
export default function Waveform({ feed }: { feed: Feed }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const stroke = useRef("#57b8ec");
  const level = useAudioLevel(feed);

  useEffect(() => {
    const c = canvas.current, g = c?.getContext("2d");
    if (!c || !g) return;
    stroke.current = getComputedStyle(c).getPropertyValue("--accent").trim() || stroke.current;
    g.fillStyle = SPEC_BG; g.fillRect(0, 0, WW, WH);
  }, []);

  useFeedEvent(feed, "audio", (a) => {
    const c = canvas.current, g = c?.getContext("2d");
    if (!c || !g) return;
    g.fillStyle = "rgba(0,0,4,0.6)"; g.fillRect(0, 0, WW, WH); // afterglow
    const s = a.samples, n = s.length, mid = WH / 2, gain = mid * 0.9;
    g.beginPath();
    for (let i = 0; i < n; i++) {
      const x = (i / (n - 1)) * WW, y = mid - s[i] * gain;
      if (i) g.lineTo(x, y); else g.moveTo(x, y);
    }
    g.strokeStyle = stroke.current; g.lineWidth = 1.5; g.lineJoin = "round"; g.stroke();
  });

  const pct = level === null ? 0 : Math.max(0, Math.min(100, ((level + 60) / 60) * 100));
  return (
    <>
      <div className="spec-wrap">
        <div className="spec-y" aria-hidden="true">
          {Y_TICKS.map(([v, label]) => <span key={v} style={{ top: yPct(v) }}>{label}</span>)}
        </div>
        <div className="spec-box">
          <canvas className="scope" ref={canvas} width={WW} height={WH} aria-label="Live waveform" />
          <div className="spec-grid" aria-hidden="true">
            {GRID.map((v) => <i key={v} className={v === 0 ? "zero" : undefined} style={{ top: yPct(v) }} />)}
          </div>
        </div>
      </div>
      <div className="spec-x" aria-hidden="true"><span>0 ms</span><span>32</span><span>64</span><span>96</span><span>128 ms</span></div>
      <div className="level">
        <span className="eyebrow">Level</span>
        <span className="level-bar"><i style={{ width: pct + "%" }} /></span>
        <span className="level-val">{level === null ? "— dB" : level.toFixed(1) + " dB"}</span>
      </div>
    </>
  );
}
