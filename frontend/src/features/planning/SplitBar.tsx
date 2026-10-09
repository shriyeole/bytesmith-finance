import React from 'react';
import type { Split } from '../../api/plan';
import { inr } from './format';

/** Needs / wants / savings as one horizontal bar of income. */
export const SplitBar: React.FC<{ split: Split; compact?: boolean }> = ({ split, compact }) => {
  const parts = [
    { key: 'needs', label: 'Needs', paise: split.needs_paise, bps: split.needs_bps },
    { key: 'wants', label: 'Wants', paise: split.wants_paise, bps: split.wants_bps },
    { key: 'savings', label: 'Saving', paise: split.savings_paise, bps: split.savings_bps },
  ];
  return (
    <div className="split">
      <div className="split__bar" role="img" aria-label={parts.map((p) => `${p.label} ${Math.round((p.bps ?? 0) / 100)}%`).join(', ')}>
        {parts.map((p) => (
          <div key={p.key} className={`split__seg split__seg--${p.key}`} style={{ width: `${Math.max(0, (p.bps ?? 0) / 100)}%` }} />
        ))}
      </div>
      {!compact && (
        <div className="split__legend">
          {parts.map((p) => (
            <span key={p.key} className="split__item">
              <i className={`split__dot split__seg--${p.key}`} />
              {p.label} <strong>{Math.round((p.bps ?? 0) / 100)}%</strong> <span className="muted">{inr(p.paise)}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
};

/** A min–max range on a 0–100% track, with an optional current-value marker. */
export const RangeTrack: React.FC<{ min: number; max: number; current?: number | null }> = ({ min, max, current }) => (
  <div className="range-track" role="img" aria-label={`Range ${min}% to ${max}%${current != null ? `, now ${current}%` : ''}`}>
    <div className="range-track__band" style={{ left: `${min}%`, width: `${Math.max(1, max - min)}%` }} />
    {current != null && <div className="range-track__now" style={{ left: `${Math.min(100, current)}%` }} />}
  </div>
);
