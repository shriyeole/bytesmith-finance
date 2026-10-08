import React from 'react';
import { Link } from 'react-router-dom';
import { useHousehold, useOnboarding, useSummary } from '../api/financialState';
import { MetricTile } from '../components/common/MetricTile';
import { formatCompactINR, bpsToPercent } from '../utils/money';
import { formatINR } from '../utils/currency';

const pct = (bps: number | null | undefined) => (bps === null || bps === undefined ? '—' : `${bpsToPercent(bps)}%`);

export const OverviewPage: React.FC = () => {
  const summary = useSummary();
  const onboarding = useOnboarding();
  const household = useHousehold();
  const s = summary.data;
  const ob = onboarding.data;

  return (
    <div className="page-container">
      <header className="page-header-row">
        <div>
          <h1 className="page-title">{household.data?.full_name ? `Hi ${household.data.full_name.split(' ')[0]}` : 'Your money today'}</h1>
          <p className="page-subtitle">Where you stand right now, from what you have entered.</p>
        </div>
      </header>

      {ob && !ob.is_complete && (
        <div className="callout-box callout-box--info">
          <div className="callout-box__content">
            <p className="callout-box__title">Setup {ob.completed_count} of {ob.total_count} done</p>
            <p className="callout-box__sub">Finish the remaining steps so these numbers reflect your full picture.</p>
          </div>
          <Link className="btn btn--primary btn--sm" to={`/setup/${ob.next_step === 'liabilities' ? 'loans' : ob.next_step ?? 'profile'}`}>Continue setup</Link>
        </div>
      )}

      {summary.isLoading && <p className="muted">Loading…</p>}
      {summary.isError && <div className="form-alert form-alert--error">{(summary.error as Error).message}</div>}

      {s && (
        <>
          <h2 className="section-heading">Position</h2>
          <div className="tile-grid">
            <MetricTile label="Net worth" value={formatCompactINR(s.net_worth_paise)} subtitle={`${formatCompactINR(s.total_assets_paise)} assets − ${formatCompactINR(s.total_liabilities_paise)} owed`} />
            <MetricTile label="Usable cash" value={formatCompactINR(s.liquid_assets_paise)} subtitle={`Emergency fund ${formatCompactINR(s.emergency_fund_paise)}`} />
            <MetricTile label="Emergency runway" value={s.emergency_runway_months === null || s.emergency_runway_months === undefined ? '—' : `${s.emergency_runway_months} months`} subtitle="Usable cash ÷ essential spend, premiums and EMIs" />
            <MetricTile label="High-cost debt" value={formatCompactINR(s.high_cost_debt_paise)} subtitle="Credit cards and loans at 14%+" />
          </div>

          <h2 className="section-heading">Every month</h2>
          <div className="tile-grid">
            <MetricTile label="Income" value={formatINR(s.monthly_income_paise)} />
            <MetricTile label="Spending" value={formatINR(s.monthly_essential_expenses_paise + s.monthly_discretionary_expenses_paise)} subtitle={`${formatINR(s.monthly_essential_expenses_paise)} essential · ${formatINR(s.monthly_discretionary_expenses_paise)} discretionary`} />
            <MetricTile label="EMIs & premiums" value={formatINR(s.monthly_emi_paise + s.monthly_insurance_premiums_paise)} subtitle={`Debt-to-income ${pct(s.debt_to_income_bps)}`} />
            <MetricTile label="Surplus" value={formatINR(s.monthly_surplus_paise)} subtitle={`Savings rate ${pct(s.savings_rate_bps)} · ${formatINR(s.monthly_planned_investments_paise)} already invested`} />
          </div>

          <h2 className="section-heading">Protection</h2>
          <div className="tile-grid">
            <MetricTile label="Health cover" value={formatCompactINR(s.health_cover_paise)} />
            <MetricTile label="Life cover" value={formatCompactINR(s.life_cover_paise)} />
            <MetricTile label="Dependents" value={String(s.dependents_count)} />
          </div>

          {s.notes.length > 0 && (
            <div className="callout-box callout-box--neutral mt-3">
              <div className="callout-box__content">
                <p className="callout-box__title">Worth checking</p>
                <ul className="plain-list">{s.notes.map((n) => <li key={n}>{n}</li>)}</ul>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
};
