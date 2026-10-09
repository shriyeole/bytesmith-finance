import React, { useEffect, useState } from 'react';
import { useAllocation, useFeatures, useRiskQuestions, useSaveRiskAnswers } from '../api/plan';
import { duration } from '../features/planning/format';
import { RangeTrack } from '../features/planning/SplitBar';
import { Method } from '../features/planning/ui';

const CLASS_LABEL: Record<string, string> = { equity: 'Equity', fixed_income: 'Fixed income', gold: 'Gold', cash: 'Cash' };
const POSITION: Record<string, string> = { below: 'Below range', within: 'Within range', above: 'Above range' };

export const InvestingPage: React.FC = () => {
  const features = useFeatures();
  const enabled = features.data?.allocation === true;
  const questions = useRiskQuestions(enabled);
  const view = useAllocation(enabled);
  const save = useSaveRiskAnswers();
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [editing, setEditing] = useState(false);
  const v = view.data;

  useEffect(() => {
    if (v && !v.risk.answered) setEditing(true);
  }, [v]);

  if (features.isSuccess && !enabled) {
    return <div className="page-container"><h1 className="page-title">Investing mix</h1><div className="card"><p className="muted">This section is not available yet.</p></div></div>;
  }

  const allAnswered = (questions.data ?? []).every((q) => answers[q.id]);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    await save.mutateAsync(answers);
    setEditing(false);
  };

  return (
    <div className="page-container">
      <header className="page-header-row">
        <div>
          <h1 className="page-title">Investing mix</h1>
          <p className="page-subtitle">How money for each goal could be spread across asset classes, given when you need it and how much risk suits you.</p>
        </div>
      </header>
      {v && <div className="callout-box callout-box--info"><div className="callout-box__content"><p className="callout-box__sub">{v.disclaimer}</p></div></div>}
      {(view.isLoading || features.isLoading) && <p className="muted">Loading…</p>}

      {v && editing && questions.data && (
        <form className="card risk-form" onSubmit={submit}>
          <h2 className="card__title">Four quick questions</h2>
          {questions.data.map((q) => (
            <fieldset key={q.id} className="risk-q">
              <legend className="risk-q__text">{q.text}</legend>
              <div className="risk-q__options">
                {q.options.map((o) => (
                  <label key={o.value} className={`risk-opt ${answers[q.id] === o.value ? 'risk-opt--on' : ''}`}>
                    <input type="radio" name={q.id} value={o.value} checked={answers[q.id] === o.value} onChange={() => setAnswers((a) => ({ ...a, [q.id]: o.value }))} />
                    {o.label}
                  </label>
                ))}
              </div>
            </fieldset>
          ))}
          {save.isError && <div className="form-alert form-alert--error">{(save.error as Error).message}</div>}
          <div className="form-actions-row">
            {v.risk.answered && <button type="button" className="btn btn--outline" onClick={() => setEditing(false)}>Cancel</button>}
            <button type="submit" className="btn btn--primary" disabled={!allAnswered || save.isPending}>See my mix</button>
          </div>
        </form>
      )}

      {v && v.risk.answered && !editing && (
        <>
          <section className="card risk-card">
            <div className="numbers__head">
              <div>
                <span className="stat__label">Your risk profile</span>
                <h2 className="risk-card__band">{v.risk.final_name}</h2>
              </div>
              <button type="button" className="btn btn--outline btn--sm" onClick={() => setEditing(true)}>Change answers</button>
            </div>
            <div className="risk-scales">
              <div><span className="stat__label">Willing to take</span><div className="band-dots">{[1, 2, 3, 4, 5].map((i) => <i key={i} className={i <= (v.risk.willingness_band ?? 0) ? 'on' : ''} />)}</div></div>
              <div><span className="stat__label">Able to take</span><div className="band-dots">{[1, 2, 3, 4, 5].map((i) => <i key={i} className={i <= v.risk.capacity_band ? 'on' : ''} />)}</div></div>
              <div><span className="stat__label">Equity ceiling</span><strong>{v.risk.equity_cap_pct}%</strong></div>
            </div>
            <p className="muted">
              {v.risk.limiting_factor === 'capacity' ? 'Your finances, not your appetite, set the limit here: ' :
                v.risk.limiting_factor === 'willingness' ? 'Your comfort with ups and downs sets the limit. ' : 'Your appetite and your finances agree. '}
              {v.risk.limiting_factor !== 'willingness' && v.risk.capacity_reasons.join(' ')}
            </p>
          </section>

          {v.goals.length === 0 ? <div className="card"><p className="muted">Add goals with a date to see ranges for each.</p></div> : (
            <section className="card">
              <h2 className="card__title">Ranges for each goal</h2>
              <div className="alloc-goals">
                {v.goals.map((g) => (
                  <div key={g.goal_id ?? g.name} className="alloc-goal">
                    <div className="alloc-goal__head"><strong>{g.name}</strong><span className="muted">{g.horizon_label} · {duration(g.months_left)}</span></div>
                    {g.ranges.map((r) => (
                      <div key={r.asset_class} className="alloc-row">
                        <span className="alloc-row__label">{CLASS_LABEL[r.asset_class]}</span>
                        <RangeTrack min={r.min_pct} max={r.max_pct} />
                        <span className="alloc-row__value">{r.min_pct}–{r.max_pct}%</span>
                      </div>
                    ))}
                    {g.notes.map((n) => <p key={n} className="data-table__note">{n}</p>)}
                  </div>
                ))}
              </div>
            </section>
          )}

          <section className="card">
            <h2 className="card__title">What you hold now vs the overall range</h2>
            {v.invested_paise === 0 ? <p className="muted">Add savings and investments in My finances to compare.</p> : (
              <div className="alloc-goals">
                {v.current_mix.map((m) => (
                  <div key={m.asset_class} className="alloc-row">
                    <span className="alloc-row__label">{CLASS_LABEL[m.asset_class]}</span>
                    {m.target_min_pct != null && m.target_max_pct != null ? <RangeTrack min={m.target_min_pct} max={m.target_max_pct} current={m.current_pct} /> : <span />}
                    <span className="alloc-row__value">
                      {m.current_pct ?? 0}% now{m.position && <span className={`pill pill--inline pill--${m.position === 'within' ? 'good' : 'warn'}`}>{POSITION[m.position]}</span>}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </section>
          <Method lines={v.method} />
        </>
      )}
    </div>
  );
};
