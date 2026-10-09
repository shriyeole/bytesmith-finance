import React, { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { useHousehold } from '../api/financialState';
import { GoalCreate, previewGoal, useDebounced, useGoal, useGoalMutations } from '../api/planning';
import { day, duration, GOAL_TYPES, inr, inrShort, pct, PRIORITIES, share } from '../features/planning/format';
import { Pill, Stat } from '../features/planning/ui';
import { bpsToPercent, paiseToRupees, percentToBps, rupeesToPaise } from '../utils/money';

type Form = {
  goal_type: string; name: string; priority: string; target_date: string; cost: string; saved: string;
  monthly: string; down_payment: string; inflation: string; ret: string; notes: string;
};
const EMPTY: Form = { goal_type: '', name: '', priority: '', target_date: '', cost: '', saved: '', monthly: '', down_payment: '', inflation: '', ret: '', notes: '' };

function toBody(f: Form): GoalCreate {
  const body: Record<string, unknown> = { name: f.name.trim() || 'My goal', goal_type: f.goal_type };
  if (f.priority) body.priority = f.priority;
  if (f.goal_type !== 'retirement' && f.target_date) body.target_date = f.target_date;
  const money = (label: string, v: string) => {
    try { return rupeesToPaise(v); } catch (e) { throw new Error(`${label}: ${(e as Error).message}`); }
  };
  const percent = (label: string, v: string) => {
    try { return percentToBps(v); } catch (e) { throw new Error(`${label}: ${(e as Error).message}`); }
  };
  const cost = money('Cost', f.cost);
  if (cost !== null) body.current_cost_paise = cost;
  body.saved_paise = money('Already saved', f.saved) ?? 0;
  body.monthly_contribution_paise = money('Monthly amount', f.monthly) ?? 0;
  const dp = percent('Down payment', f.down_payment);
  if (f.goal_type === 'home' && dp !== null) body.down_payment_bps = dp;
  const inf = percent('Inflation', f.inflation);
  if (inf !== null) body.inflation_bps = inf;
  const r = percent('Expected return', f.ret);
  if (r !== null) body.expected_return_bps = r;
  if (f.notes.trim()) body.notes = f.notes.trim();
  return body as GoalCreate;
}

export const GoalEditorPage: React.FC = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const existing = useGoal(id);
  const household = useHousehold();
  const { create, update } = useGoalMutations();
  const [form, setForm] = useState<Form>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof Form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  useEffect(() => {
    const g = existing.data;
    if (!g) return;
    setForm({
      goal_type: g.goal_type, name: g.name, priority: g.priority, target_date: g.target_date ?? '',
      cost: paiseToRupees(g.current_cost_paise), saved: paiseToRupees(g.saved_paise), monthly: paiseToRupees(g.monthly_contribution_paise),
      down_payment: bpsToPercent(g.down_payment_bps), inflation: bpsToPercent(g.inflation_bps), ret: bpsToPercent(g.expected_return_bps),
      notes: g.notes ?? '',
    });
  }, [existing.data]);

  const isRetirement = form.goal_type === 'retirement';
  const body = useMemo(() => {
    try { return { ok: true as const, value: toBody(form) }; } catch (e) { return { ok: false as const, error: (e as Error).message }; }
  }, [form]);
  const debounced = useDebounced(body);
  // Decide from the debounced values, not the live form, so a stale body is never sent.
  const canPreview = debounced.ok && !!debounced.value.goal_type &&
    (debounced.value.goal_type === 'retirement' || (!!debounced.value.target_date && !!debounced.value.current_cost_paise));
  const preview = useQuery({
    queryKey: ['goal-preview', debounced],
    queryFn: () => previewGoal((debounced as { value: GoalCreate }).value),
    enabled: canPreview,
    retry: false,
  });

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!body.ok) return setError(body.error);
    try {
      const saved = id ? await update.mutateAsync({ id, body: body.value }) : await create.mutateAsync(body.value);
      navigate(`/goals/${saved.id}`);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  if (!form.goal_type) {
    return (
      <div className="page-container">
        <header className="page-header-row"><div><h1 className="page-title">What are you saving for?</h1></div></header>
        <div className="type-grid">
          {GOAL_TYPES.map((t) => (
            <button key={t.value} type="button" className="card type-card" onClick={() => setForm({ ...EMPTY, goal_type: t.value, name: t.value === 'other' ? '' : t.label })}>
              <span className="type-card__label">{t.label}</span>
              <span className="type-card__hint">{t.hint}</span>
            </button>
          ))}
        </div>
      </div>
    );
  }

  const ev = preview.data;
  return (
    <div className="page-container">
      <header className="page-header-row">
        <div>
          <h1 className="page-title">{id ? 'Edit goal' : GOAL_TYPES.find((t) => t.value === form.goal_type)?.label}</h1>
          <p className="page-subtitle">Enter costs in today’s money — we add inflation for you.</p>
        </div>
      </header>
      <div className="editor-layout">
        <form className="card editor-form" onSubmit={submit} noValidate>
          <div className="form-grid form-grid--2">
            <div className="form-field"><label className="form-field__label" htmlFor="g-name">Name</label>
              <input id="g-name" className="text-input" value={form.name} onChange={set('name')} /></div>
            <div className="form-field"><label className="form-field__label" htmlFor="g-priority">Priority</label>
              <select id="g-priority" className="text-input" value={form.priority} onChange={set('priority')}>
                <option value="">Suggested for this goal</option>
                {PRIORITIES.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
              </select></div>
            {isRetirement ? (
              <div className="form-field form-field--wide">
                <p className="form-field__helper">
                  Retirement date comes from your profile: age {household.data?.retirement_age ?? '—'}.
                  Change it in My finances → About you, or try other ages on the goal page.
                </p>
              </div>
            ) : (
              <div className="form-field"><label className="form-field__label" htmlFor="g-date">Target date</label>
                <input id="g-date" type="date" className="text-input" value={form.target_date} onChange={set('target_date')} /></div>
            )}
            <div className="form-field"><label className="form-field__label" htmlFor="g-cost">{isRetirement ? 'Monthly spending in retirement (today’s ₹)' : form.goal_type === 'home' ? 'Home price today' : 'Cost today'}</label>
              <div className="currency-input-wrapper"><span className="currency-input-prefix">₹</span>
                <input id="g-cost" className="currency-input" inputMode="decimal" value={form.cost} placeholder={isRetirement ? 'Blank = your current spending' : '0'} onChange={set('cost')} /></div></div>
            <div className="form-field"><label className="form-field__label" htmlFor="g-saved">Already saved for this</label>
              <div className="currency-input-wrapper"><span className="currency-input-prefix">₹</span>
                <input id="g-saved" className="currency-input" inputMode="decimal" value={form.saved} placeholder="0" onChange={set('saved')} /></div></div>
            <div className="form-field"><label className="form-field__label" htmlFor="g-monthly">Putting in every month</label>
              <div className="currency-input-wrapper"><span className="currency-input-prefix">₹</span>
                <input id="g-monthly" className="currency-input" inputMode="decimal" value={form.monthly} placeholder="0" onChange={set('monthly')} /></div>
              <p className="form-field__helper">Can be part of an existing SIP.</p></div>
            {form.goal_type === 'home' && (
              <div className="form-field"><label className="form-field__label" htmlFor="g-dp">Down payment %</label>
                <input id="g-dp" className="text-input" inputMode="decimal" value={form.down_payment} placeholder="20" onChange={set('down_payment')} /></div>
            )}
          </div>
          <details className="method">
            <summary>Advanced: inflation and return</summary>
            <div className="form-grid form-grid--2">
              <div className="form-field"><label className="form-field__label" htmlFor="g-inf">Inflation % a year</label>
                <input id="g-inf" className="text-input" inputMode="decimal" value={form.inflation} placeholder={`Default ${pct(ev?.inflation_bps)}`} onChange={set('inflation')} /></div>
              <div className="form-field"><label className="form-field__label" htmlFor="g-ret">Expected return % a year</label>
                <input id="g-ret" className="text-input" inputMode="decimal" value={form.ret} placeholder={`Default ${pct(ev?.return_bps)}`} onChange={set('ret')} /></div>
            </div>
          </details>
          {error && <div className="form-alert form-alert--error" role="alert">{error}</div>}
          {!body.ok && <div className="form-alert form-alert--error">{body.error}</div>}
          <div className="form-actions-row">
            <button type="button" className="btn btn--outline" onClick={() => (id ? navigate(`/goals/${id}`) : setForm(EMPTY))}>{id ? 'Cancel' : 'Back'}</button>
            <button type="submit" className="btn btn--primary" disabled={create.isPending || update.isPending}>{id ? 'Save changes' : 'Save goal'}</button>
          </div>
        </form>

        <aside className="card preview-panel" aria-live="polite">
          <h2 className="card__title">Preview</h2>
          {!canPreview && <p className="muted">{isRetirement ? 'Calculating…' : 'Add a date and a cost to see the numbers.'}</p>}
          {preview.isError && <p className="form-alert form-alert--error">{(preview.error as Error).message}</p>}
          {canPreview && ev && (ev.status === 'needs_info' ? <p className="muted">{ev.messages[0]}</p> : (
            <>
              <Pill status={ev.status} />
              <Stat label={isRetirement ? 'Corpus needed at retirement' : form.goal_type === 'home' ? 'Down payment + costs needed' : 'Cost on the day'} value={inrShort(ev.savings_target_paise)} sub={`${day(ev.target_date)} · ${duration(ev.months_left)} away`} strong />
              <Stat label="Save every month" value={inr(ev.required_monthly_paise)} sub={`at ${pct(ev.return_bps)} expected return`} />
              {ev.home_loan && <Stat label="Home loan EMI later" value={inr(ev.home_loan.emi_paise)} sub={`${inrShort(ev.home_loan.loan_paise)} loan · ${share(ev.home_loan.emi_to_income_bps)} of today's income`} />}
              {ev.retirement && <Stat label="Monthly spend at retirement" value={inr(ev.retirement.monthly_spend_at_retirement_paise)} sub={`${inr(ev.retirement.monthly_spend_today_paise)} today, for ${ev.retirement.years_in_retirement} years`} />}
              {ev.messages.map((m) => <p key={m} className="preview-panel__msg">{m}</p>)}
            </>
          ))}
        </aside>
      </div>
    </div>
  );
};
