import React, { useMemo, useState } from 'react';
import { Journey, runWhatIf, useJourney, WhatIf, WhatIfComparison } from '../api/journey';
import { ChartSeries, JourneyChart } from '../components/charts/JourneyChart';
import { day, inr, inrShort, share } from '../features/planning/format';
import { Method, Stat } from '../features/planning/ui';
import { percentToBps } from '../utils/money';

type Preset = { id: string; label: string; build: (j: Journey) => WhatIf };
const LAKH = 100_000 * 100;
const PRESETS: Preset[] = [
  { id: 'flat', label: 'Salary stays flat', build: () => ({ salary_growth_bps: 0 }) },
  { id: 'break6', label: '6-month career break next year', build: () => ({ career_break: { start_in_months: 12, months: 6 } }) },
  { id: 'break12', label: '1-year career break next year', build: () => ({ career_break: { start_in_months: 12, months: 12 } }) },
  { id: 'spend', label: 'Spend 20% less on wants', build: () => ({ spend_change_bps: -2000 }) },
  { id: 'early', label: 'Retire 5 years earlier', build: (j) => ({ retirement_age: Math.max(30, (j.summary.retirement_age ?? 60) - 5) }) },
  { id: 'late', label: 'Retire 3 years later', build: (j) => ({ retirement_age: Math.min(85, (j.summary.retirement_age ?? 60) + 3) }) },
  { id: 'car', label: 'Buy a ₹15L car in 2 years', build: () => ({ extra_goals: [{ name: 'New car', goal_type: 'car', cost_today_paise: 15 * LAKH, in_months: 24 }] }) },
  { id: 'home', label: 'Buy a ₹1 Cr home in 5 years', build: () => ({ extra_goals: [{ name: 'New home', goal_type: 'home', cost_today_paise: 100 * LAKH, in_months: 60 }] }) },
  { id: 'child', label: 'Have a child next year', build: () => ({ child: { in_months: 12 } }) },
  { id: 'windfall', label: 'Get ₹5L one-time', build: () => ({ windfall: { in_months: 0, amount_paise: 5 * LAKH } }) },
];

const KIND_LABEL: Record<string, string> = {
  goal: 'Goal paid', goal_short: 'Goal short', loan_closed: 'Loan closed', retirement: 'Retirement', depleted: 'Savings run out',
  career_break: 'Career break', child: 'Child', windfall: 'Windfall',
};

export const JourneyPage: React.FC = () => {
  const q = useJourney();
  const [real, setReal] = useState(true);
  const [active, setActive] = useState<string | null>(null);
  const [cmp, setCmp] = useState<WhatIfComparison | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [custom, setCustom] = useState({ growth: '', spend: '', age: '' });
  const j = q.data;

  const run = async (id: string, w: WhatIf) => {
    setErr(null);
    setBusy(true);
    setActive(id);
    try {
      setCmp(await runWhatIf(w));
    } catch (e) {
      setErr((e as Error).message);
      setCmp(null);
    } finally {
      setBusy(false);
    }
  };

  const series = useMemo<ChartSeries[]>(() => {
    if (!j) return [];
    const toSeries = (jr: Journey, id: string, label: string): ChartSeries => ({
      id, label, points: jr.points.map((p) => ({ month: p.month, age: p.age, year: p.year, value: real ? p.net_worth_real_paise : p.net_worth_paise })),
    });
    const s = [toSeries(j.base, 'base', 'Expected'), toSeries(j.stress, 'stress', 'Tough times'), toSeries(j.upside, 'upside', 'Things go well')];
    if (cmp) s.push(toSeries(cmp.what_if, 'whatif', 'With your change'));
    return s;
  }, [j, cmp, real]);

  if (q.isLoading) return <div className="page-container"><p className="muted">Projecting…</p></div>;
  if (q.isError || !j) return <div className="page-container"><div className="form-alert form-alert--error">{(q.error as Error)?.message ?? 'Could not load'}</div></div>;
  const b = j.base.summary;
  const shown = cmp ? cmp.what_if : j.base;

  return (
    <div className="page-container">
      <header className="page-header-row">
        <div>
          <h1 className="page-title">Wealth journey</h1>
          <p className="page-subtitle">Your net worth year by year, if things go as expected, badly, or well.</p>
        </div>
        <div className="seg" role="group" aria-label="Show values in">
          <button type="button" className={real ? 'seg--on' : ''} onClick={() => setReal(true)} aria-pressed={real}>Today's money</button>
          <button type="button" className={!real ? 'seg--on' : ''} onClick={() => setReal(false)} aria-pressed={!real}>Future rupees</button>
        </div>
      </header>

      <section className="card funding-strip">
        <Stat label={`Net worth at ${b.retirement_age ?? 'retirement'}`} value={inrShort(real ? b.net_worth_at_retirement_real_paise : b.net_worth_at_retirement_paise)} sub={real ? "in today's money" : 'in future rupees'} strong />
        <Stat label="Money lasts to" value={b.depleted_age ? `Age ${b.depleted_age}` : `Age ${b.money_lasts_to_age}+`} sub={b.depleted_age ? 'savings run out' : 'end of plan'} bad={!!b.depleted_age} />
        <Stat label="Tough times" value={j.stress.summary.depleted_age ? `Runs out at ${j.stress.summary.depleted_age}` : 'Still lasts'} sub={`${inrShort(real ? j.stress.summary.net_worth_at_retirement_real_paise : j.stress.summary.net_worth_at_retirement_paise)} at retirement`} bad={!!j.stress.summary.depleted_age} />
        <Stat label="Goals paid in full" value={`${b.goals_fully_funded} of ${b.goals_total}`} sub={b.retirement_readiness_bps != null ? `Retirement ${share(b.retirement_readiness_bps)} funded` : undefined} />
      </section>

      <section className="card">
        <JourneyChart series={series} ariaLabel="Projected net worth by age for each scenario"
          markers={shown.milestones.map((m) => ({ month: m.month, label: m.label, kind: m.kind }))} />
      </section>

      <section className="card what-if">
        <h2 className="card__title">What if…</h2>
        <p className="card__subtitle">Pick a change to see it on the chart against your expected path. Nothing is saved.</p>
        <div className="preset-row">
          {PRESETS.map((p) => (
            <button key={p.id} type="button" className={`chip ${active === p.id ? 'chip--on' : ''}`} disabled={busy} onClick={() => run(p.id, p.build(j.base))}>{p.label}</button>
          ))}
          {cmp && <button type="button" className="btn-link" onClick={() => { setCmp(null); setActive(null); }}>Clear</button>}
        </div>
        <form className="form-grid form-grid--3 custom-whatif" onSubmit={(e) => {
          e.preventDefault();
          try {
            const w: WhatIf = {};
            const g = percentToBps(custom.growth, true); if (g !== null) w.salary_growth_bps = g;
            const sp = percentToBps(custom.spend, true); if (sp !== null) w.spend_change_bps = sp;
            if (custom.age.trim()) w.retirement_age = Number(custom.age);
            run('custom', w);
          } catch (ex) { setErr((ex as Error).message); }
        }}>
          <div className="form-field"><label className="form-field__label" htmlFor="wi-g">Yearly raise %</label><input id="wi-g" className="text-input" inputMode="decimal" placeholder={`${(j.base.params.salary_growth_bps ?? 0) / 100}`} value={custom.growth} onChange={(e) => setCustom({ ...custom, growth: e.target.value })} /></div>
          <div className="form-field"><label className="form-field__label" htmlFor="wi-s">Change wants spending %</label><input id="wi-s" className="text-input" inputMode="decimal" placeholder="e.g. -15" value={custom.spend} onChange={(e) => setCustom({ ...custom, spend: e.target.value })} /></div>
          <div className="form-field"><label className="form-field__label" htmlFor="wi-a">Retire at age</label><input id="wi-a" className="text-input" inputMode="numeric" placeholder={`${b.retirement_age ?? ''}`} value={custom.age} onChange={(e) => setCustom({ ...custom, age: e.target.value })} /></div>
          <div className="form-actions-row form-field--wide"><button type="submit" className="btn btn--outline" disabled={busy}>Try my numbers</button></div>
        </form>
        {err && <div className="form-alert form-alert--error">{err}</div>}
        {cmp && (
          <div className="whatif-result" aria-live="polite">
            {cmp.lines.map((l) => <p key={l} className="whatif-result__line">{l}</p>)}
          </div>
        )}
      </section>

      <section className="card">
        <h2 className="card__title">Milestones {cmp ? '(with your change)' : ''}</h2>
        {shown.milestones.length === 0 ? <p className="muted">No milestones yet. Add goals to see them here.</p> : (
          <ul className="milestones">
            {shown.milestones.map((m, i) => (
              <li key={i} className={`milestone milestone--${m.kind}`}>
                <span className="milestone__when">{day(m.date)}{m.age != null ? ` · age ${m.age}` : ''}</span>
                <span className="milestone__kind">{KIND_LABEL[m.kind] ?? m.kind}</span>
                <span className="milestone__label">{m.label}{m.amount_paise ? ` · ${inr(Math.round(m.amount_paise / 100) * 100)}` : ''}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <Method lines={[...j.notes, ...j.assumptions]} />
    </div>
  );
};
