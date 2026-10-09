import React, { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useSaveHousehold } from '../api/financialState';
import { GoalEvaluation, GoalWhatIf, useDebounced, useGoal, useGoalEvaluation, useGoalMutations, whatIfGoal } from '../api/planning';
import { day, duration, goalTypeLabel, inr, inrShort, pct, priorityLabel, share } from '../features/planning/format';
import { Method, Pill, Progress, Stat } from '../features/planning/ui';
import { paiseToRupees, rupeesToPaise } from '../utils/money';

const Numbers: React.FC<{ e: GoalEvaluation; title: string }> = ({ e, title }) => (
  <div className="card numbers">
    <div className="numbers__head"><h2 className="card__title">{title}</h2><Pill status={e.status} /></div>
    {e.status === 'needs_info' ? <p className="muted">{e.messages[0]}</p> : (
      <>
        <Progress bps={e.funded_bps} tone={e.status === 'on_track' ? 'good' : e.status === 'at_risk' ? 'warn' : 'bad'} />
        <div className="numbers__grid">
          <Stat label="Needed by the date" value={inrShort(e.savings_target_paise)} sub={`${day(e.target_date)} · ${duration(e.months_left)}`} strong />
          <Stat label="You'll have" value={inrShort(e.projected_paise)} sub={`${share(e.funded_bps)} of target`} />
          <Stat label="Save per month" value={inr(e.required_monthly_paise)} sub={`now ${inr(e.current_monthly_paise)}`} />
          <Stat label="At current pace" value={e.months_to_reach_at_current === null || e.months_to_reach_at_current === undefined ? 'Not reached' : day(e.reach_date_at_current)} sub={e.monthly_gap_paise ? `short by ${inr(e.monthly_gap_paise)}/month` : 'on time'} />
        </div>
      </>
    )}
  </div>
);

export const GoalDetailPage: React.FC = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const goal = useGoal(id);
  const evaluation = useGoalEvaluation(id);
  const { update, remove } = useGoalMutations();
  const saveHousehold = useSaveHousehold();
  const g = goal.data;
  const e = evaluation.data;
  const isRet = g?.goal_type === 'retirement';

  const [date, setDate] = useState('');
  const [monthly, setMonthly] = useState('');
  const [saved, setSaved] = useState('');
  const [retAge, setRetAge] = useState('');
  useEffect(() => {
    if (!g || !e) return;
    setDate(g.target_date ?? '');
    setMonthly(paiseToRupees(g.monthly_contribution_paise));
    setSaved(paiseToRupees(g.saved_paise));
    setRetAge(e.retirement ? String(e.retirement.retirement_age) : '');
  }, [g, e]);

  const overrides = useMemo<{ ok: boolean; body: GoalWhatIf; changed: boolean }>(() => {
    if (!g) return { ok: false, body: {}, changed: false };
    try {
      const body: GoalWhatIf = {};
      const m = rupeesToPaise(monthly);
      const s = rupeesToPaise(saved);
      if (m !== null && m !== g.monthly_contribution_paise) body.monthly_contribution_paise = m;
      if (s !== null && s !== g.saved_paise) body.saved_paise = s;
      if (!isRet && date && date !== g.target_date) body.target_date = date;
      if (isRet && /^\d+$/.test(retAge) && Number(retAge) !== e?.retirement?.retirement_age) body.retirement_age = Number(retAge);
      return { ok: true, body, changed: Object.keys(body).length > 0 };
    } catch {
      return { ok: false, body: {}, changed: false };
    }
  }, [g, e, monthly, saved, date, retAge, isRet]);
  const debounced = useDebounced(overrides);
  const whatIf = useQuery({
    queryKey: ['what-if', id, debounced.body],
    queryFn: () => whatIfGoal(id!, debounced.body),
    enabled: !!id && debounced.ok && debounced.changed,
    retry: false,
  });

  const apply = async () => {
    if (!id || !g) return;
    const { retirement_age, ...goalChanges } = overrides.body;
    if (Object.keys(goalChanges).length) await update.mutateAsync({ id, body: goalChanges });
    if (retirement_age !== undefined) await saveHousehold.mutateAsync({ retirement_age });
  };

  if (goal.isError) return <div className="page-container"><div className="form-alert form-alert--error">Goal not found.</div></div>;
  if (!g || !e) return <div className="page-container"><p className="muted">Loading…</p></div>;

  return (
    <div className="page-container">
      <Link to="/goals" className="btn-back">← All goals</Link>
      <header className="page-header-row">
        <div>
          <h1 className="page-title">{g.name}</h1>
          <p className="page-subtitle">{goalTypeLabel(g.goal_type)} · {priorityLabel(g.priority)}{g.status !== 'active' ? ` · ${g.status}` : ''}</p>
        </div>
        <div className="header-actions">
          <Link to={`/goals/${g.id}/edit`} className="btn btn--outline btn--sm">Edit</Link>
          {g.status !== 'achieved'
            ? <button type="button" className="btn btn--outline btn--sm" onClick={() => update.mutate({ id: g.id, body: { status: 'achieved' } })}>Mark achieved</button>
            : <button type="button" className="btn btn--outline btn--sm" onClick={() => update.mutate({ id: g.id, body: { status: 'active' } })}>Reopen</button>}
          <button type="button" className="btn btn--danger btn--sm" onClick={async () => { await remove.mutateAsync(g.id); navigate('/goals'); }}>Delete</button>
        </div>
      </header>

      <Numbers e={e} title="Current plan" />
      {e.messages.length > 0 && <div className="callout-box callout-box--neutral"><div className="callout-box__content">{e.messages.map((m) => <p key={m} className="callout-box__sub">{m}</p>)}</div></div>}

      {e.home_loan && (
        <section className="card">
          <h2 className="card__title">The home loan you would take</h2>
          <div className="numbers__grid">
            <Stat label="Price on the day" value={inrShort(e.home_loan.price_at_purchase_paise)} />
            <Stat label="Down payment + costs" value={inrShort(e.home_loan.down_payment_paise + e.home_loan.extra_costs_paise)} />
            <Stat label="Loan" value={inrShort(e.home_loan.loan_paise)} sub={`${pct(e.home_loan.loan_rate_bps)} for ${e.home_loan.loan_months / 12} yrs`} />
            <Stat label="EMI" value={inr(e.home_loan.emi_paise)} sub={`${share(e.home_loan.emi_to_income_bps)} of today's take-home`} bad={e.home_loan.affordable === false} />
          </div>
        </section>
      )}
      {e.retirement && (
        <section className="card">
          <h2 className="card__title">Your retirement</h2>
          <div className="numbers__grid">
            <Stat label="Retire on" value={day(e.retirement.retirement_date)} sub={`at age ${e.retirement.retirement_age}`} />
            <Stat label="Monthly spend then" value={inr(e.retirement.monthly_spend_at_retirement_paise)} sub={`${inr(e.retirement.monthly_spend_today_paise)} in today's money`} />
            <Stat label="Planned for" value={`${e.retirement.years_in_retirement} years`} sub={`corpus earning ${pct(e.retirement.post_retirement_return_bps)}`} />
          </div>
        </section>
      )}

      {g.status === 'active' && (
        <section className="card what-if">
          <h2 className="card__title">What if…</h2>
          <p className="card__subtitle">Try changes here. Nothing is saved until you press “Use these numbers”.</p>
          <div className="form-grid form-grid--3">
            {isRet ? (
              <div className="form-field"><label className="form-field__label" htmlFor="w-age">Retire at age</label>
                <input id="w-age" className="text-input" inputMode="numeric" value={retAge} onChange={(ev) => setRetAge(ev.target.value)} /></div>
            ) : (
              <div className="form-field"><label className="form-field__label" htmlFor="w-date">Target date</label>
                <input id="w-date" type="date" className="text-input" value={date} onChange={(ev) => setDate(ev.target.value)} /></div>
            )}
            <div className="form-field"><label className="form-field__label" htmlFor="w-monthly">Monthly amount</label>
              <div className="currency-input-wrapper"><span className="currency-input-prefix">₹</span>
                <input id="w-monthly" className="currency-input" inputMode="decimal" value={monthly} onChange={(ev) => setMonthly(ev.target.value)} /></div></div>
            <div className="form-field"><label className="form-field__label" htmlFor="w-saved">Already saved</label>
              <div className="currency-input-wrapper"><span className="currency-input-prefix">₹</span>
                <input id="w-saved" className="currency-input" inputMode="decimal" value={saved} onChange={(ev) => setSaved(ev.target.value)} /></div></div>
          </div>
          {overrides.changed && whatIf.data && <Numbers e={whatIf.data} title="With these changes" />}
          {whatIf.isError && <div className="form-alert form-alert--error">{(whatIf.error as Error).message}</div>}
          {overrides.changed && (
            <div className="form-actions-row">
              <button type="button" className="btn btn--primary" disabled={update.isPending || saveHousehold.isPending} onClick={apply}>Use these numbers</button>
            </div>
          )}
        </section>
      )}

      <Method lines={[
        `Cost grows at ${pct(e.inflation_bps)} a year; savings grow at ${pct(e.return_bps)} a year (assumed, not guaranteed).`,
        'Monthly amounts are invested at the start of each month.',
        ...(e.goal_type === 'home' ? ['You save the down payment and purchase costs; the rest is a home loan.'] : []),
        ...(e.goal_type === 'retirement' ? ['The corpus pays your inflation-adjusted monthly spending from retirement to age 85.'] : []),
      ]} />
    </div>
  );
};
