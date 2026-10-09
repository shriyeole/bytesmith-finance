import React, { useState } from 'react';
import { RuleResult, useBudget, useChooseBudget } from '../api/plan';
import { inr, share } from '../features/planning/format';
import { SplitBar } from '../features/planning/SplitBar';
import { Method, Stat } from '../features/planning/ui';
import { percentToBps } from '../utils/money';

const RuleCard: React.FC<{ r: RuleResult; onChoose: () => void; busy: boolean }> = ({ r, onChoose, busy }) => (
  <article className={`card rule-card ${r.recommended ? 'rule-card--recommended' : ''} ${r.selected ? 'rule-card--selected' : ''}`}>
    <div className="rule-card__head">
      <div>
        <h3 className="rule-card__name">{r.name}</h3>
        <p className="muted">{r.description}</p>
      </div>
      <div className="rule-card__badges">
        {r.recommended && <span className="pill pill--good">Best fit</span>}
        {r.selected && <span className="pill pill--neutral">Your rule</span>}
        {!r.feasible && <span className="pill pill--warn">{r.id === 'goal_first' ? 'Short of goals' : "Essentials don't fit"}</span>}
      </div>
    </div>
    <SplitBar split={r.plan} />
    <div className="rule-card__stats">
      <Stat label="Saving each month" value={inr(r.plan.savings_paise)} sub={r.savings_increase_paise ? `+${inr(r.savings_increase_paise)} vs now` : 'same as now'} />
      <Stat label="Goals & safety funded" value={share(r.coverage_bps)} bad={r.coverage_bps < 10000} />
      <Stat label="Lifestyle change" value={r.wants_cut_paise ? `−${inr(r.wants_cut_paise)}` : 'None'} sub="per month on wants" />
    </div>
    <p className="rule-card__tradeoff">{r.tradeoff}</p>
    {!r.selected && <button type="button" className="btn btn--outline btn--sm" disabled={busy} onClick={onChoose}>Use this rule</button>}
  </article>
);

export const BudgetPage: React.FC = () => {
  const q = useBudget();
  const choose = useChooseBudget();
  const [savings, setSavings] = useState('');
  const [wants, setWants] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const b = q.data;

  const saveCustom = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    try {
      const s = percentToBps(savings);
      if (s === null) throw new Error('Enter how much of your income you want to save.');
      await choose.mutateAsync({ rule: 'custom', custom_savings_bps: s, custom_wants_bps: percentToBps(wants) });
    } catch (ex) {
      setErr((ex as Error).message);
    }
  };

  return (
    <div className="page-container">
      <header className="page-header-row">
        <div>
          <h1 className="page-title">Budget</h1>
          <p className="page-subtitle">Popular budgeting rules, tested on your real numbers: what each one funds and what it asks you to give up.</p>
        </div>
      </header>
      {q.isLoading && <p className="muted">Loading…</p>}
      {q.isError && <div className="form-alert form-alert--error">{(q.error as Error).message}</div>}
      {b && b.status === 'needs_info' && <div className="card"><p className="muted">{b.messages[0]}</p></div>}
      {b && b.status === 'ok' && (
        <>
          <section className="card budget-now">
            <h2 className="card__title">Your month today</h2>
            <SplitBar split={b.current} />
            <div className="numbers__grid">
              <Stat label="Income" value={inr(b.income_paise)} />
              <Stat label="Goals need" value={inr(b.goals_need_paise)} sub="per month" />
              <Stat label="Safety net needs" value={inr(b.safety_need_paise)} sub="emergency fund + expensive debt, over 12 months" />
              <Stat label="Total to set aside" value={inr(b.total_need_paise)} strong />
            </div>
            {b.messages.map((m) => <p key={m} className="callout-box__sub">{m}</p>)}
          </section>

          <div className="rule-grid">
            {[...b.rules].sort((x, y) => Number(y.recommended) - Number(x.recommended)).map((r) => (
              <RuleCard key={r.id} r={r} busy={choose.isPending} onChoose={() => choose.mutate({ rule: r.id })} />
            ))}
          </div>

          <form className="card custom-rule" onSubmit={saveCustom}>
            <h2 className="card__title">Make your own rule</h2>
            <div className="form-grid form-grid--3">
              <div className="form-field"><label className="form-field__label" htmlFor="c-save">Save % of income</label>
                <input id="c-save" className="text-input" inputMode="decimal" value={savings} placeholder="e.g. 35" onChange={(e) => setSavings(e.target.value)} /></div>
              <div className="form-field"><label className="form-field__label" htmlFor="c-wants">Wants % of income</label>
                <input id="c-wants" className="text-input" inputMode="decimal" value={wants} placeholder="optional" onChange={(e) => setWants(e.target.value)} /></div>
              <div className="form-field custom-rule__submit"><button type="submit" className="btn btn--primary" disabled={choose.isPending}>Compare my rule</button></div>
            </div>
            {err && <div className="form-alert form-alert--error">{err}</div>}
            {choose.isError && <div className="form-alert form-alert--error">{(choose.error as Error).message}</div>}
          </form>
          <Method lines={b.method} />
        </>
      )}
    </div>
  );
};
