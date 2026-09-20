"use client";
import { useEffect, useRef } from "react";
import type { Feed } from "@/lib/feed";
import { useFeedEvent } from "@/lib/hooks";

const WW = 600, WH = 160;

// Oscilloscope of the raw hydrophone signal, before the FFT: each audio frame
// (256 samples at 2 kHz, 128 ms) is drawn as one trace over a short afterglow.
// The canvas is transparent, so it sits on the map as a tint, not a block.
export default function Waveform({ feed }: { feed: Feed }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const stroke = useRef("#57b8ec");

  useEffect(() => {
    const c = canvas.current;
    if (c) stroke.current = getComputedStyle(c).getPropertyValue("--accent").trim() || stroke.current;
  }, []);

  useFeedEvent(feed, "audio", (a) => {
    const c = canvas.current, g = c?.getContext("2d");
    if (!c || !g) return;
    // afterglow: fade what is there instead of painting a background over it
    g.globalCompositeOperation = "destination-out";
    g.fillStyle = "rgba(0,0,0,0.55)"; g.fillRect(0, 0, WW, WH);
    g.globalCompositeOperation = "source-over";
    const s = a.samples, n = s.length, mid = WH / 2, gain = mid * 0.9;
    g.beginPath();
    for (let i = 0; i < n; i++) {
      const x = (i / (n - 1)) * WW, y = mid - s[i] * gain;
      if (i) g.lineTo(x, y); else g.moveTo(x, y);
    }
    g.strokeStyle = stroke.current; g.lineWidth = 1.5; g.lineJoin = "round"; g.stroke();
  });

  return (
    <div className="scope-box">
      <canvas className="scope" ref={canvas} width={WW} height={WH} aria-label="Live waveform, last 128 ms" />
      <i className="scope-zero" aria-hidden="true" />
    </div>
  );
}
