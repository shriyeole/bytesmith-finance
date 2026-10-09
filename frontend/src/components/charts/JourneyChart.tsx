/**
 * Net worth over time for up to four scenarios. Hand-built SVG:
 * 2px lines, hairline grid, one y-axis, legend + direct end labels, crosshair tooltip,
 * milestone markers on the first series, and a table view for accessibility.
 * Colours are validated categorical slots 1–4 (see dataviz palette check).
 */

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { formatCompactINR } from '../../utils/money';

export interface ChartPoint { month: number; age?: number | null; year: number; value: number }
export interface ChartSeries { id: string; label: string; points: ChartPoint[] }
export interface ChartMarker { month: number; label: string; kind: string }

const COLORS = ['var(--series-1)', 'var(--series-2)', 'var(--series-3)', 'var(--series-4)'];
const PAD = { top: 16, right: 92, bottom: 30, left: 64 };

function niceTicks(min: number, max: number, count = 5): number[] {
  const span = max - min || 1;
  const raw = span / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => span / s <= count) ?? raw;
  const start = Math.floor(min / step) * step;
  const ticks: number[] = [];
  for (let v = start; v <= max + step * 0.5; v += step) ticks.push(Math.round(v));
  return ticks;
}

export const JourneyChart: React.FC<{
  series: ChartSeries[];
  markers?: ChartMarker[];
  xLabel?: (p: ChartPoint) => string;
  height?: number;
  compact?: boolean;
  ariaLabel: string;
}> = ({ series, markers = [], xLabel = (p) => (p.age != null ? `Age ${p.age}` : String(p.year)), height = 320, compact = false, ariaLabel }) => {
  const wrap = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(720);
  const [hover, setHover] = useState<number | null>(null);
  const [showTable, setShowTable] = useState(false);

  useEffect(() => {
    if (!wrap.current) return;
    const ro = new ResizeObserver((entries) => setWidth(Math.max(280, Math.floor(entries[0].contentRect.width))));
    ro.observe(wrap.current);
    return () => ro.disconnect();
  }, []);

  const pad = compact ? { top: 8, right: 12, bottom: 22, left: 52 } : { ...PAD, right: width < 520 ? 16 : PAD.right };
  const base = series[0]?.points ?? [];
  const months = base.map((p) => p.month);
  const maxMonth = Math.max(1, ...months);
  const all = series.flatMap((s) => s.points.map((p) => p.value));
  const yMin = Math.min(0, ...all);
  const yMax = Math.max(1, ...all);
  const ticks = useMemo(() => niceTicks(yMin, yMax, compact ? 3 : 5), [yMin, yMax, compact]);
  const lo = Math.min(yMin, ticks[0]);
  const hi = Math.max(yMax, ticks[ticks.length - 1]);
  const iw = width - pad.left - pad.right;
  const ih = height - pad.top - pad.bottom;
  const x = (m: number) => pad.left + (m / maxMonth) * iw;
  const y = (v: number) => pad.top + ih - ((v - lo) / (hi - lo || 1)) * ih;
  const path = (pts: ChartPoint[]) => pts.map((p, i) => `${i ? 'L' : 'M'}${x(p.month).toFixed(1)},${y(p.value).toFixed(1)}`).join('');
  const xTickIdx = base.map((_, i) => i).filter((i) => i % Math.max(1, Math.ceil(base.length / (width < 520 ? 4 : 8))) === 0);

  const onMove = (e: React.PointerEvent<SVGRectElement>) => {
    const rect = (e.target as SVGRectElement).getBoundingClientRect();
    const m = ((e.clientX - rect.left) / rect.width) * maxMonth;
    let best = 0;
    base.forEach((p, i) => { if (Math.abs(p.month - m) < Math.abs(base[best].month - m)) best = i; });
    setHover(best);
  };

  const hp = hover != null ? base[hover] : null;
  const markerAt = (m: number) => {
    // place markers on the first series, interpolated between yearly points
    const i = base.findIndex((p) => p.month >= m);
    if (i <= 0) return base[0]?.value ?? 0;
    const a = base[i - 1], b = base[i];
    return a.value + ((b.value - a.value) * (m - a.month)) / (b.month - a.month || 1);
  };

  // direct labels at line ends, nudged apart only if they would overlap
  const ends = series.map((s, i) => ({ i, label: s.label, yv: y(s.points[s.points.length - 1]?.value ?? 0) })).sort((a, b) => a.yv - b.yv);
  for (let k = 1; k < ends.length; k++) if (ends[k].yv - ends[k - 1].yv < 14) ends[k].yv = ends[k - 1].yv + 14;

  return (
    <div className="jchart" ref={wrap}>
      {!compact && series.length > 1 && (
        <div className="jchart__legend" aria-hidden="true">
          {series.map((s, i) => <span key={s.id} className="jchart__key"><i style={{ background: COLORS[i] }} />{s.label}</span>)}
        </div>
      )}
      <svg width={width} height={height} role="img" aria-label={ariaLabel} className="jchart__svg">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.left} x2={width - pad.right} y1={y(t)} y2={y(t)} className={t === 0 ? 'jchart__zero' : 'jchart__grid'} />
            <text x={pad.left - 8} y={y(t) + 4} textAnchor="end" className="jchart__tick">{formatCompactINR(t)}</text>
          </g>
        ))}
        {xTickIdx.map((i) => (
          <text key={i} x={x(base[i].month)} y={height - 8} textAnchor="middle" className="jchart__tick">{xLabel(base[i])}</text>
        ))}
        {series.map((s, i) => (
          <path key={s.id} d={path(s.points)} fill="none" stroke={COLORS[i]} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        ))}
        {!compact && markers.map((mk, i) => (
          <g key={i}>
            <circle cx={x(mk.month)} cy={y(markerAt(mk.month))} r={5} className={`jchart__marker jchart__marker--${mk.kind}`}>
              <title>{mk.label}</title>
            </circle>
          </g>
        ))}
        {!compact && width >= 520 && ends.map((e) => (
          <text key={e.i} x={width - pad.right + 8} y={e.yv + 4} className="jchart__end">{e.label}</text>
        ))}
        {hp && (
          <g pointerEvents="none">
            <line x1={x(hp.month)} x2={x(hp.month)} y1={pad.top} y2={pad.top + ih} className="jchart__cross" />
            {series.map((s, i) => s.points[hover!] && (
              <circle key={s.id} cx={x(s.points[hover!].month)} cy={y(s.points[hover!].value)} r={4} fill={COLORS[i]} className="jchart__dot" />
            ))}
          </g>
        )}
        <rect x={pad.left} y={pad.top} width={iw} height={ih} fill="transparent" onPointerMove={onMove} onPointerLeave={() => setHover(null)} />
      </svg>
      {hp && (
        <div className="jchart__tip" style={{ left: Math.min(width - 190, Math.max(0, x(hp.month) + 12)), top: pad.top }} role="status">
          <strong>{xLabel(hp)} · {hp.year}</strong>
          {series.map((s, i) => s.points[hover!] && (
            <span key={s.id}><i style={{ background: COLORS[i] }} />{s.label}<b>{formatCompactINR(s.points[hover!].value)}</b></span>
          ))}
        </div>
      )}
      {!compact && (
        <>
          <button type="button" className="btn-link jchart__tablebtn" onClick={() => setShowTable(!showTable)}>{showTable ? 'Hide' : 'Show'} as table</button>
          {showTable && (
            <div className="table-wrap">
              <table className="data-table">
                <thead><tr><th>When</th>{series.map((s) => <th key={s.id}>{s.label}</th>)}</tr></thead>
                <tbody>
                  {base.map((p, i) => (
                    <tr key={p.month}><td>{xLabel(p)} ({p.year})</td>{series.map((s) => <td key={s.id}>{formatCompactINR(s.points[i]?.value)}</td>)}</tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
};
