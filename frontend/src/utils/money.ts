/**
 * Exact string <-> integer conversions for form inputs. No floating point is used,
 * so "1234.56" becomes exactly 123456 paise and "8.5" % becomes exactly 850 bps.
 */

export function rupeesToPaise(raw: string): number | null {
  const cleaned = raw.replace(/[₹,\s]/g, '');
  if (cleaned === '') return null;
  const m = /^(\d+)(?:\.(\d{1,2}))?$/.exec(cleaned);
  if (!m) throw new Error('Enter an amount like 25000 or 25000.50');
  const paise = Number(m[1]) * 100 + Number((m[2] ?? '').padEnd(2, '0'));
  if (!Number.isSafeInteger(paise)) throw new Error('Amount is too large');
  return paise;
}

export function paiseToRupees(paise: number | null | undefined): string {
  if (paise === null || paise === undefined) return '';
  const rupees = Math.trunc(paise / 100);
  const rest = Math.abs(paise % 100);
  return rest ? `${rupees}.${String(rest).padStart(2, '0')}` : String(rupees);
}

/** "8", "8.5", "8.25" (%) -> basis points. Negative allowed only when allowNegative. */
export function percentToBps(raw: string, allowNegative = false): number | null {
  const cleaned = raw.replace(/[%\s]/g, '');
  if (cleaned === '') return null;
  const m = /^(-?)(\d+)(?:\.(\d{1,2}))?$/.exec(cleaned);
  if (!m || (m[1] && !allowNegative)) throw new Error('Enter a percentage like 8 or 8.5');
  const bps = Number(m[2]) * 100 + Number((m[3] ?? '').padEnd(2, '0'));
  return m[1] ? -bps : bps;
}

export function bpsToPercent(bps: number | null | undefined): string {
  if (bps === null || bps === undefined) return '';
  const sign = bps < 0 ? '-' : '';
  const abs = Math.abs(bps);
  const whole = Math.trunc(abs / 100);
  const rest = abs % 100;
  return rest ? `${sign}${whole}.${String(rest).padStart(2, '0').replace(/0$/, '')}` : `${sign}${whole}`;
}

/** Compact Indian format for tiles: ₹12.5L, ₹1.2Cr, ₹45,000. */
export function formatCompactINR(paise: number | null | undefined): string {
  if (paise === null || paise === undefined) return '—';
  const sign = paise < 0 ? '-' : '';
  const rupees = Math.abs(paise) / 100;
  if (rupees >= 1e7) return `${sign}₹${(rupees / 1e7).toFixed(2).replace(/\.?0+$/, '')}Cr`;
  if (rupees >= 1e5) return `${sign}₹${(rupees / 1e5).toFixed(2).replace(/\.?0+$/, '')}L`;
  return `${sign}₹${Math.round(rupees).toLocaleString('en-IN')}`;
}
