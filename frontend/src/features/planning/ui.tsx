import React from 'react';
import { STATUS_LABEL, STATUS_TONE } from './format';

export const Pill: React.FC<{ status: string; label?: string }> = ({ status, label }) => (
  <span className={`pill pill--${STATUS_TONE[status] ?? 'neutral'}`}>{label ?? STATUS_LABEL[status] ?? status}</span>
);

export const Progress: React.FC<{ bps: number | null | undefined; tone?: string }> = ({ bps, tone }) => {
  const pctVal = Math.max(0, Math.min(100, (bps ?? 0) / 100));
  return (
    <div className="progress" role="progressbar" aria-valuenow={Math.round(pctVal)} aria-valuemin={0} aria-valuemax={100}>
      <div className={`progress__fill progress__fill--${tone ?? 'neutral'}`} style={{ width: `${pctVal}%` }} />
    </div>
  );
};

export const Stat: React.FC<{ label: string; value: React.ReactNode; sub?: React.ReactNode; strong?: boolean; bad?: boolean }> = ({ label, value, sub, strong, bad }) => (
  <div className={`stat ${strong ? 'stat--strong' : ''} ${bad ? 'stat--bad' : ''}`}>
    <span className="stat__label">{label}</span>
    <span className="stat__value">{value}</span>
    {sub && <span className="stat__sub">{sub}</span>}
  </div>
);

export const Method: React.FC<{ lines: string[]; title?: string }> = ({ lines, title = 'How we worked this out' }) =>
  lines.length ? (
    <details className="method">
      <summary>{title}</summary>
      <ul>{lines.map((l) => <li key={l}>{l}</li>)}</ul>
    </details>
  ) : null;
