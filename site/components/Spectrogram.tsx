"use client";
import { useRef } from "react";
import type { Feed } from "@/lib/feed";
import { melOf, MEL_MAX, seaCss } from "@/lib/dsp";
import { useFeedEvent } from "@/lib/hooks";

const SW = 600, SH = 160;

// Scrolling mel spectrogram: each audio frame shifts the canvas one pixel left
// and paints its 80 bins down the right edge. Quiet bins are transparent
// (see the sea ramp in lib/dsp.ts), so the map shows through the noise floor.
export default function Spectrogram({ feed }: { feed: Feed }) {
  const canvas = useRef<HTMLCanvasElement>(null);

  useFeedEvent(feed, "audio", (a) => {
    const c = canvas.current, g = c?.getContext("2d");
    if (!c || !g) return;
    // "copy" replaces every pixel with the shifted image, transparent ones included;
    // source-over would stack the translucent haze on itself each frame.
    g.globalCompositeOperation = "copy";
    g.drawImage(c, -1, 0);
    g.globalCompositeOperation = "source-over";
    const b = a.bins, n = b.length;
    for (let i = 0; i < n; i++) {
      const y0 = SH - melOf((i + 1) / n * 1000) / MEL_MAX * SH, y1 = SH - melOf(i / n * 1000) / MEL_MAX * SH;
      g.fillStyle = seaCss(b[i]); g.fillRect(SW - 1, y0, 1, Math.ceil(y1 - y0));
    }
  });

  return (
    <div className="scope-box">
      <canvas id="spec" className="scope" ref={canvas} width={SW} height={SH} aria-label="Live spectrogram, 0 to 1 kHz, last 30 seconds" />
    </div>
  );
}
