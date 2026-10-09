import React from 'react';
import { Link } from 'react-router-dom';
import { GoalEvaluation, useGoalsPlan } from '../api/planning';
import { day, duration, goalTypeLabel, inr, inrShort, priorityLabel, share, STATUS_TONE } from '../features/planning/format';
import { Method, Pill, Progress, Stat } from '../features/planning/ui';

const GoalCard: React.FC<{ e: GoalEvaluation; allocated?: number }> = ({ e, allocated }) => (
  <Link to={`/goals/${e.goal_id}`} className="card goal-card">
    <div className="goal-card__head">
      <div>
        <span className="goal-card__type">{goalTypeLabel(e.goal_type)} · {priorityLabel(e.priority)}</span>
        <h3 className="goal-card__name">{e.name}</h3>
      </div>
      <Pill status={e.status} />
    </div>
    {e.status === 'needs_info' ? (
      <p className="muted">{e.messages[0]}</p>
    ) : (
      <>
        <div className="goal-card__progress">
          <Progress bps={e.funded_bps} tone={STATUS_TONE[e.status]} />
          <span className="goal-card__pct">{share(e.funded_bps)} funded by the date</span>
        </div>
        <div className="goal-card__stats">
          <Stat label="Needed" value={inrShort(e.savings_target_paise)} sub={`by ${day(e.target_date)} · ${duration(e.months_left)}`} />
          <Stat label="Monthly needed" value={inr(e.required_monthly_paise)} sub={`You put in ${inr(e.current_monthly_paise)}`} />
        </div>
        {allocated !== undefined && e.required_monthly_paise !== null && e.required_monthly_paise !== undefined && allocated < e.required_monthly_paise && (
          <p className="goal-card__note">Your surplus covers {inr(allocated)} of this after higher-priority goals.</p>
        )}
      </>
    )}
  </Link>
);

export const GoalsPage: React.FC = () => {
  const plan = useGoalsPlan();
  const p = plan.data;
  const allocated = new Map((p?.allocation ?? []).map((a) => [a.goal_id, a.allocated_paise]));
  const active = (p?.goals ?? []).filter((g) => g.goal_status !== 'achieved' && g.status !== 'achieved');
  const done = (p?.goals ?? []).filter((g) => g.goal_status === 'achieved' || g.status === 'achieved');

  return (
    <div className="page-container">
      <header className="page-header-row">
        <div>
          <h1 className="page-title">Goals</h1>
          <p className="page-subtitle">What each goal will cost by its date, and what you need to put aside every month.</p>
        </div>
        <Link to="/goals/new" className="btn btn--primary">+ Add goal</Link>
      </header>

      {plan.isLoading && <p className="muted">Loading…</p>}
      {plan.isError && <div className="form-alert form-alert--error">{(plan.error as Error).message}</div>}

      {p && p.goals.length === 0 && (
        <div className="card card-empty-state">
          <h2 className="card__title">No goals yet</h2>
          <p className="muted">Start with retirement, then add the big things you are saving for: a home, a car, your child's education.</p>
          <Link to="/goals/new" className="btn btn--primary">Add your first goal</Link>
        </div>
      )}

      {p && p.goals.length > 0 && (
        <>
          <section className="card funding-strip">
            <Stat label="Monthly surplus" value={inr(p.monthly_surplus_paise)} sub="Income minus spending, EMIs and premiums" />
            <Stat label="Goals need" value={inr(p.total_required_monthly_paise)} sub="Per month, to stay on track" />
            <Stat label="You put in now" value={inr(p.total_current_monthly_paise)} />
            <Stat label="Shortfall" value={inr(p.unfunded_monthly_paise)} bad={p.unfunded_monthly_paise > 0} sub={p.unfunded_monthly_paise > 0 ? 'Not covered by your surplus' : 'Surplus covers every goal'} />
          </section>
          {p.messages.map((m) => <div key={m} className="callout-box callout-box--neutral"><div className="callout-box__content"><p className="callout-box__sub">{m}</p></div></div>)}

          <div className="goal-grid">
            {active.map((e) => <GoalCard key={e.goal_id} e={e} allocated={allocated.get(e.goal_id ?? '')} />)}
          </div>
          {done.length > 0 && (
            <>
              <h2 className="section-heading">Achieved</h2>
              <div className="goal-grid">{done.map((e) => <GoalCard key={e.goal_id} e={e} />)}</div>
            </>
          )}
          <Method lines={[
            'Each goal’s cost is grown by inflation to its date; savings grow at an expected return that is more cautious for nearer goals.',
            'When your surplus cannot cover everything, money goes to Essential goals first, then Important, then Nice to have.',
            ...p.assumptions,
          ]} />
        </>
      )}
    </div>
  );
};
