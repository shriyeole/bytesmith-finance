import { formatINR } from '../../utils/currency';
import { bpsToPercent, formatCompactINR } from '../../utils/money';
import { formatDate } from '../../utils/date';

export const inr = (p: number | null | undefined) => formatINR(p ?? null);
export const inrShort = (p: number | null | undefined) => formatCompactINR(p ?? null);
export const pct = (bps: number | null | undefined) => (bps === null || bps === undefined ? '—' : `${bpsToPercent(bps)}%`);
/** Share of a target, as a whole percentage ("66%"). */
export const share = (bps: number | null | undefined) => (bps === null || bps === undefined ? '—' : `${Math.round(bps / 100)}%`);
export const day = (d: string | null | undefined) => formatDate(d ?? null);

export function duration(months: number | null | undefined): string {
  if (months === null || months === undefined) return '—';
  if (months <= 0) return 'now';
  const y = Math.floor(months / 12);
  const m = months % 12;
  return [y ? `${y} yr${y > 1 ? 's' : ''}` : '', m ? `${m} mo` : ''].filter(Boolean).join(' ');
}

export const STATUS_LABEL: Record<string, string> = {
  on_track: 'On track', at_risk: 'At risk', off_track: 'Off track', achieved: 'Achieved', needs_info: 'Needs info',
  good: 'Good', attention: 'Needs attention', critical: 'Act now', none: 'No loans', not_needed: 'Not needed',
};
export const STATUS_TONE: Record<string, 'good' | 'warn' | 'bad' | 'neutral'> = {
  on_track: 'good', achieved: 'good', good: 'good', none: 'good', not_needed: 'neutral',
  at_risk: 'warn', attention: 'warn', off_track: 'bad', critical: 'bad', needs_info: 'neutral',
};

export const GOAL_TYPES: { value: string; label: string; hint: string }[] = [
  { value: 'retirement', label: 'Retirement', hint: 'Build a corpus to live on after you stop working' },
  { value: 'home', label: 'Buy a home', hint: 'Save the down payment; we check the loan EMI' },
  { value: 'child_education', label: "Child's education", hint: 'College or school fees (education costs rise faster)' },
  { value: 'car', label: 'Car', hint: 'A car or bike purchase' },
  { value: 'wedding', label: 'Wedding / family event', hint: 'Wedding or another big family occasion' },
  { value: 'travel', label: 'Travel', hint: 'A big trip' },
  { value: 'big_purchase', label: 'Big purchase', hint: 'Gadgets, furniture, renovation' },
  { value: 'other', label: 'Something else', hint: 'Any other goal with a date and a cost' },
];
export const goalTypeLabel = (t: string) => GOAL_TYPES.find((g) => g.value === t)?.label ?? t;
export const PRIORITIES = [
  { value: 'essential', label: 'Essential' },
  { value: 'important', label: 'Important' },
  { value: 'aspirational', label: 'Nice to have' },
];
export const priorityLabel = (p: string) => PRIORITIES.find((x) => x.value === p)?.label ?? p;
