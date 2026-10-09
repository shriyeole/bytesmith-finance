import React from 'react';
import { Link } from 'react-router-dom';
import { AlertRead, HealthScore, useActions, useAlertMutations, useHealth, useJourney } from '../../api/journey';
import { JourneyChart } from '../../components/charts/JourneyChart';
import { inrShort } from './format';

const SEVERITY_LABEL: Record<string, string> = { critical: 'Urgent', warning: 'Important', attention: 'Worth a look', opportunity: 'Opportunity', info: 'FYI' };
export const severityLabel = (s: string) => SEVERITY_LABEL[s] ?? s;

const Ring: React.FC<{ score: number; band: string }> = ({ score, band }) => {
  const r = 42, c = 2 * Math.PI * r;
  return (
    <svg width="104" height="104" viewBox="0 0 104 104" className={`ring ring--${band}`} role="img" aria-label={`Health score ${score} out of 100`}>
      <circle cx="52" cy="52" r={r} className="ring__track" />
      <circle cx="52" cy="52" r={r} className="ring__value" strokeDasharray={`${(score / 100) * c} ${c}`} transform="rotate(-90 52 52)" />
      <text x="52" y="58" textAnchor="middle" className="ring__text">{score}</text>
    </svg>
  );
};

export const HealthCard: React.FC<{ h: HealthScore }> = ({ h }) => (
  <section className="card health">
    <div className="health__head">
      <Ring score={h.score} band={h.band} />
      <div>
        <span className="stat__label">Financial health</span>
        <h2 className="health__label">{h.label}</h2>
        <p className="muted">{h.score} of 100 · five areas, 20 points each</p>
      </div>
    </div>
    <ul className="health__parts">
      {h.parts.map((p) => (
        <li key={p.key} className="health__part">
          <div className="health__row">
            <Link to={p.link} className="health__name">{p.name}</Link>
            <span className="health__pts">{p.points}/{p.max_points}</span>
          </div>
          <div className="progress"><div className={`progress__fill progress__fill--${p.points >= 16 ? 'good' : p.points >= 8 ? 'warn' : 'bad'}`} style={{ width: `${(p.points / p.max_points) * 100}%` }} /></div>
          <span className="health__detail">{p.detail}{p.tip ? ` ${p.tip}` : ''}</span>
        </li>
      ))}
    </ul>
  </section>
);

export const ActionCard: React.FC<{ a: AlertRead; compact?: boolean }> = ({ a, compact }) => {
  const { done, dismiss, snooze } = useAlertMutations();
  return (
    <article className={`card action action--${a.severity}`}>
      <div className="action__top">
        <span className={`sev sev--${a.severity}`}>{severityLabel(a.severity)}</span>
        {a.impact_paise ? <span className="muted action__impact">at stake ~{inrShort(a.impact_paise)}</span> : null}
      </div>
      <h3 className="action__title">{a.title}</h3>
      <p className="action__msg">{a.message}</p>
      <div className="action__buttons">
        {a.action_link && <Link to={a.action_link} className="btn btn--primary btn--sm">{a.action_label ?? 'Open'}</Link>}
        <button type="button" className="btn btn--outline btn--sm" onClick={() => done.mutate(a.id)}>Done</button>
        {!compact && <button type="button" className="btn btn--outline btn--sm" title="Hide for 7 days" onClick={() => snooze.mutate({ id: a.id, days: 7 })}>Snooze a week</button>}
        <button type="button" className="btn-link" onClick={() => dismiss.mutate(a.id)}>Dismiss</button>
      </div>
    </article>
  );
};

export const DashboardExtras: React.FC = () => {
  const health = useHealth();
  const actions = useActions();
  const journey = useJourney();
  const j = journey.data;
  return (
    <div className="dash-extras">
      <div className="dash-extras__row">
        {health.data && <HealthCard h={health.data} />}
        <section className="dash-actions">
          <div className="numbers__head"><h2 className="section-heading">Do next</h2><Link to="/alerts" className="btn-link">All alerts →</Link></div>
          {actions.data && actions.data.length === 0 && <div className="card"><p className="muted">Nothing urgent. Nice.</p></div>}
          {actions.data?.map((a) => <ActionCard key={a.id} a={a} compact />)}
        </section>
      </div>
      {j && (
        <Link to="/journey" className="card journey-mini">
          <div className="numbers__head">
            <div>
              <span className="stat__label">Wealth journey (today's money)</span>
              <strong className="journey-mini__headline">
                {inrShort(j.base.summary.net_worth_at_retirement_real_paise)} at {j.base.summary.retirement_age ?? 'retirement'}
                {j.base.summary.depleted_age ? ` · savings run out at ${j.base.summary.depleted_age}` : ` · lasts to ${j.base.summary.money_lasts_to_age}+`}
              </strong>
            </div>
            <span className="btn-link">Open →</span>
          </div>
          <JourneyChart compact height={150} ariaLabel="Expected net worth by age"
            series={[{ id: 'base', label: 'Expected', points: j.base.points.map((p) => ({ month: p.month, age: p.age, year: p.year, value: p.net_worth_real_paise })) }]} />
        </Link>
      )}
    </div>
  );
};
