import { fmt } from "../lib/format";

export interface TrendPoint {
  label: string;
  median: number;
  min: number;
  max: number;
}

const W = 480;
const H = 190;
const PAD = { left: 40, right: 20, top: 16, bottom: 32 };

/** Overall score per graded attempt: a dot for the median and a bar for the likely range. */
export default function ScoreTrend({ points, maxPossible }: { points: TrendPoint[]; maxPossible: number }) {
  if (points.length === 0) return null;
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;
  const x = (i: number) => (points.length === 1 ? PAD.left + innerW / 2 : PAD.left + (i * innerW) / (points.length - 1));
  const y = (value: number) => PAD.top + (1 - Math.min(Math.max(value / maxPossible, 0), 1)) * innerH;
  const summary = points.map((p) => `${p.label}: ${fmt(p.median)} of ${fmt(maxPossible)}`).join(", ");

  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Score trend. ${summary}`} className="w-full max-w-xl">
      {[0, 0.5, 1].map((fraction) => (
        <g key={fraction}>
          <line x1={PAD.left} x2={W - PAD.right} y1={y(fraction * maxPossible)} y2={y(fraction * maxPossible)} className="stroke-slate-200" />
          <text x={PAD.left - 6} y={y(fraction * maxPossible) + 4} textAnchor="end" className="fill-slate-500 text-[10px]">
            {fmt(fraction * maxPossible)}
          </text>
        </g>
      ))}
      {points.length > 1 && (
        <polyline fill="none" className="stroke-indigo-400" strokeWidth={2} points={points.map((p, i) => `${x(i)},${y(p.median)}`).join(" ")} />
      )}
      {points.map((p, i) => (
        <g key={p.label} data-testid="trend-point">
          <line x1={x(i)} x2={x(i)} y1={y(p.max)} y2={y(p.min)} className="stroke-indigo-300" strokeWidth={6} strokeLinecap="round" opacity={0.5} />
          <circle cx={x(i)} cy={y(p.median)} r={5} className="fill-indigo-600">
            <title>{`${p.label}: ${fmt(p.median)} (likely ${fmt(p.min)}–${fmt(p.max)})`}</title>
          </circle>
          <text x={x(i)} y={y(p.max) - 8} textAnchor="middle" className="fill-slate-800 text-[11px] font-semibold">{fmt(p.median)}</text>
          <text x={x(i)} y={H - 10} textAnchor="middle" className="fill-slate-600 text-[11px]">{p.label}</text>
        </g>
      ))}
    </svg>
  );
}
