"use client";
import { useMemo, useState } from "react";
import { DAY, type Detection } from "@/lib/detections";
import { useElementSize } from "@/lib/hooks";

const PAD_L = 28, PAD_B = 22, PAD_T = 16, N = 14;

// Detections per day, last 14 days: one series, thin bars anchored to the
// baseline, hover tooltip, one direct label on the max. The same numbers are
// listed for screen readers, so the hover tooltip is a convenience, not the
// only way to read the chart.
export default function DetectionsChart({ detections, now }: { detections: Detection[]; now: number | null }) {
  const [ref, size] = useElementSize<HTMLDivElement>();
  const W = size.width || 800, H = size.height || 140;
  const [hover, setHover] = useState<{ i: number; left: number } | null>(null);

  const day0 = useMemo(() => { const d = new Date(now ?? 0); d.setHours(0, 0, 0, 0); return d.getTime(); }, [now]);
  const days = useMemo(() => {
    const out: { t: number; n: number }[] = [];
    for (let i = N - 1; i >= 0; i--) { const t = day0 - i * DAY; out.push({ t, n: detections.filter((x) => x.t >= t && x.t < t + DAY).length }); }
    return out;
  }, [detections, day0]);

  const max = Math.max(1, ...days.map((d) => d.n)), yMax = Math.ceil(max / 2) * 2;
  const slot = (W - PAD_L) / N, bw = Math.min(28, Math.max(6, slot - 8));
  const x = (i: number) => PAD_L + i * slot;
  const y = (n: number) => PAD_T + (H - PAD_T - PAD_B) * (1 - n / yMax);
  const tip = hover ? days[hover.i] : null;
  const total = days.reduce((s, d) => s + d.n, 0);
  const short = (t: number) => new Date(t).toLocaleDateString(undefined, { month: "short", day: "numeric" });

  return (
    <>
      <div className="chart" ref={ref}>
        {now && (
          <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={total + " detections over the last 14 days; daily counts follow"}>
            {[0, yMax / 2, yMax].map((v) => (
              <g key={v}>
                <line className="grid" x1={PAD_L} x2={W} y1={y(v)} y2={y(v)} />
                <text x={PAD_L - 8} y={y(v) + 4} textAnchor="end">{v}</text>
              </g>
            ))}
            <line className="base" x1={PAD_L} x2={W} y1={y(0)} y2={y(0)} />
            {days.map((d, i) => {
              const cx = x(i) + (slot - bw) / 2, top = y(d.n), h = Math.max(0, y(0) - top);
              return (
                <g key={d.t} onMouseEnter={() => setHover({ i, left: x(i) + slot / 2 })} onMouseLeave={() => setHover(null)}>
                  <rect className="hit" x={x(i)} y={PAD_T} width={slot} height={H - PAD_T - PAD_B} />
                  {d.n > 0 && <rect className={"bar" + (hover?.i === i ? " hot" : "")} x={cx} y={top} width={bw} height={h} rx={2} />}
                  {d.n === max && d.n > 0 && <text className="dl" x={cx + bw / 2} y={top - 5} textAnchor="middle">{d.n}</text>}
                  {(i % 2 === 1 || i === N - 1) && (
                    <text x={cx + bw / 2} y={H - 6} textAnchor="middle">{short(d.t)}</text>
                  )}
                </g>
              );
            })}
          </svg>
        )}
      </div>
      {now && (
        <ul className="sr-only">
          {days.map((d) => <li key={d.t}>{short(d.t)}: {d.n}</li>)}
        </ul>
      )}
      {tip && hover && (
        <div className="tip" style={{ left: hover.left, top: y(tip.n) - 8 }} aria-hidden="true">
          {new Date(tip.t).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })} · {tip.n}{tip.n === 1 ? " detection" : " detections"}
        </div>
      )}
    </>
  );
}
