import React from 'react';
import { GoalFeasibilityResponse } from '../../api/types';
import { formatINR } from '../../utils/currency';
import {
  AlertCircleIcon,
  CalendarIcon,
  CheckCircleIcon,
  ClockIcon,
  InfoCircleIcon,
  LightbulbIcon,
  ReportsIcon,
  TagIcon,
  TrendingUpIcon,
  WalletIcon,
  XCircleIcon,
} from '../common/Icons';
import { MetricTile } from '../common/MetricTile';

interface FeasibilityAnalysisCardProps {
  feasibility: GoalFeasibilityResponse | null;
  onGoToProfile?: () => void;
  onGoToGoal?: () => void;
}

export const FeasibilityAnalysisCard: React.FC<FeasibilityAnalysisCardProps> = ({
  feasibility,
  onGoToProfile,
  onGoToGoal,
}) => {
  if (!feasibility) {
    return (
      <div className="card feasibility-card">
        <h2 className="card__title">Goal Feasibility Analysis</h2>
        <p className="card__subtitle">
          Based on your current profile and goal details.
        </p>
        <div className="card-empty-state">
          <p>Complete your financial profile and add an active goal to calculate real-time feasibility.</p>
          <div className="empty-actions-row mt-3">
            {onGoToProfile && (
              <button type="button" className="btn btn--outline btn--sm" onClick={onGoToProfile}>
                Profile Setup
              </button>
            )}
            {onGoToGoal && (
              <button type="button" className="btn btn--primary btn--sm" onClick={onGoToGoal}>
                Goal Setup
              </button>
            )}
          </div>
        </div>
      </div>
    );
  }

  const {
    feasibility_status,
    actionable_insight,
    months_remaining,
    required_monthly_savings_paise,
    baseline_monthly_surplus_paise,
    monthly_buffer_paise,
    monthly_shortfall_paise,
    required_discretionary_cut_paise,
    months_needed_at_current_surplus,
    monthly_discretionary_spend_paise,
    timeline_basis,
    missing_baseline_inputs,
  } = feasibility;

  // Status-specific banner configuration
  let bannerIcon = <CheckCircleIcon size={32} color="#16A34A" />;
  let bannerClass = 'feasibility-banner--success';
  let bannerTitle = 'Your goal is feasible!';

  if (feasibility_status === 'STRETCH_FEASIBLE') {
    bannerIcon = <AlertCircleIcon size={32} color="#D97706" />;
    bannerClass = 'feasibility-banner--warning';
    bannerTitle = 'Stretch Feasible with Discretionary Cut';
  } else if (feasibility_status === 'INFEASIBLE') {
    bannerIcon = <XCircleIcon size={32} color="#DC2626" />;
    bannerClass = 'feasibility-banner--danger';
    bannerTitle = 'Goal is Currently Infeasible';
  } else if (feasibility_status === 'INSUFFICIENT_DATA') {
    bannerIcon = <InfoCircleIcon size={32} color="#2563EB" />;
    bannerClass = 'feasibility-banner--info';
    bannerTitle = 'Insufficient Profile Data';
  }

  // Display buffer or shortfall
  let bufferLabel = 'Monthly buffer';
  let bufferValue = formatINR(monthly_buffer_paise, { fallback: '—' });
  let bufferVariant: 'default' | 'highlight' | 'warning' | 'danger' = 'default';

  if (monthly_shortfall_paise !== null && monthly_shortfall_paise > 0) {
    bufferLabel = 'Monthly shortfall';
    bufferValue = formatINR(monthly_shortfall_paise);
    bufferVariant = 'danger';
  } else if (monthly_buffer_paise !== null && monthly_buffer_paise > 0) {
    bufferVariant = 'highlight';
  }

  // Display discretionary spending or cut
  let discretionaryLabel = 'Discretionary spending';
  let discretionaryValue = formatINR(monthly_discretionary_spend_paise, { fallback: '—' });
  if (required_discretionary_cut_paise !== null && required_discretionary_cut_paise > 0) {
    discretionaryLabel = 'Required cut from discretionary';
    discretionaryValue = formatINR(required_discretionary_cut_paise);
  }

  return (
    <div className="card feasibility-card">
      <div className="card__header-row">
        <div>
          <h2 className="card__title">Goal Feasibility Analysis</h2>
          <p className="card__subtitle">
            Based on your current profile and goal details.
          </p>
        </div>
      </div>

      {/* Main Status Banner */}
      <div className={`feasibility-banner ${bannerClass}`}>
        <div className="feasibility-banner__icon">{bannerIcon}</div>
        <div className="feasibility-banner__content">
          <h3 className="feasibility-banner__title">{bannerTitle}</h3>
          <p className="feasibility-banner__desc">{actionable_insight}</p>
          {missing_baseline_inputs && missing_baseline_inputs.length > 0 && (
            <div className="feasibility-banner__missing">
              <span>Missing required fields: </span>
              <strong>{missing_baseline_inputs.join(', ')}</strong>
            </div>
          )}
        </div>
      </div>

      {/* 2x3 Metrics Grid */}
      <div className="feasibility-metrics-grid">
        <MetricTile
          icon={<CalendarIcon size={20} color="#2563EB" />}
          label="Months remaining"
          value={months_remaining !== null ? months_remaining : '—'}
        />

        <MetricTile
          icon={<TrendingUpIcon size={20} color="#2563EB" />}
          label="Required monthly savings"
          value={formatINR(required_monthly_savings_paise, { fallback: '—' })}
        />

        <MetricTile
          icon={<WalletIcon size={20} color="#2563EB" />}
          label="Your monthly surplus"
          value={formatINR(baseline_monthly_surplus_paise, { fallback: '—' })}
        />

        <MetricTile
          icon={<ReportsIcon size={20} color="#2563EB" />}
          label={bufferLabel}
          value={bufferValue}
          variant={bufferVariant}
        />

        <MetricTile
          icon={<ClockIcon size={20} color="#2563EB" />}
          label="Months needed at current surplus"
          value={
            months_needed_at_current_surplus !== null
              ? months_needed_at_current_surplus
              : '—'
          }
          subtitle={
            months_needed_at_current_surplus === null && baseline_monthly_surplus_paise !== null && baseline_monthly_surplus_paise <= 0
              ? 'Surplus is non-positive'
              : undefined
          }
        />

        <MetricTile
          icon={<TagIcon size={20} color="#2563EB" />}
          label={discretionaryLabel}
          value={discretionaryValue}
        />
      </div>

      {/* Timeline Basis Callout */}
      {timeline_basis && (
        <div className="timeline-basis-card">
          <div className="timeline-basis-card__icon">
            <LightbulbIcon size={20} color="#2563EB" />
          </div>
          <div className="timeline-basis-card__content">
            <h4 className="timeline-basis-card__title">Timeline basis</h4>
            <p className="timeline-basis-card__desc">
              {timeline_basis.explanation}
            </p>
          </div>
        </div>
      )}
    </div>
  );
};
