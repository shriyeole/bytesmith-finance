import React from 'react';
import { GoalFeasibilityResponse, GoalResponse } from '../../api/types';
import { formatINR } from '../../utils/currency';
import { formatDate } from '../../utils/date';
import { CarIcon, TargetIcon } from '../common/Icons';
import { StatusBadge } from '../common/StatusBadge';

interface CurrentGoalCardProps {
  goal: GoalResponse | null;
  feasibility: GoalFeasibilityResponse | null;
  onEditGoal: () => void;
}

export const CurrentGoalCard: React.FC<CurrentGoalCardProps> = ({
  goal,
  feasibility,
  onEditGoal,
}) => {
  if (!goal) {
    return (
      <div className="card current-goal-card">
        <div className="card__header-row">
          <h2 className="card__title">Current Goal</h2>
        </div>
        <div className="card-empty-state">
          <p>No active financial goal found. Create a goal to evaluate its feasibility against your monthly surplus.</p>
          <button
            type="button"
            className="btn btn--primary btn--sm mt-3"
            onClick={onEditGoal}
          >
            Create Financial Goal
          </button>
        </div>
      </div>
    );
  }

  // Derive progress covered by allocated savings
  const targetPaise = goal.target_amount_paise;
  const permittedPaise = goal.permitted_allocated_savings_paise;
  let coveragePct = 0;
  if (permittedPaise !== null && targetPaise > 0) {
    coveragePct = Math.min(100, Math.round((permittedPaise / targetPaise) * 100));
  }

  // Icon based on goal title
  const isVehicle = /car|bike|motorcycle|scooter|vehicle/i.test(goal.title);
  const GoalIconComponent = isVehicle ? CarIcon : TargetIcon;

  return (
    <div className="card current-goal-card">
      <div className="card__header-row">
        <h2 className="card__title">Current Goal</h2>
        <button
          type="button"
          className="btn-link"
          onClick={onEditGoal}
          aria-label="Edit or view goal details"
        >
          View Details
        </button>
      </div>

      {/* Goal Summary Header */}
      <div className="goal-summary-header">
        <div className="goal-summary-header__icon-circle">
          <GoalIconComponent size={24} color="#2563EB" />
        </div>
        <div className="goal-summary-header__content">
          <div className="goal-summary-header__title-row">
            <h3 className="goal-summary-header__title">{goal.title}</h3>
            <StatusBadge status={goal.status} variant="active" />
          </div>
          <div className="goal-summary-header__meta">
            <span>Target: <strong>{formatINR(goal.target_amount_paise)}</strong></span>
            <span className="goal-summary-header__dot">•</span>
            <span>Target date: <strong>{formatDate(goal.target_date)}</strong></span>
          </div>
        </div>
      </div>

      {/* Allocation Progress Bar */}
      <div className="goal-progress-section">
        <div className="goal-progress-header">
          <span className="goal-progress-label">
            Covered by allocated savings
          </span>
          <span className="goal-progress-pct">
            {permittedPaise !== null ? `${coveragePct}%` : 'Pending verification'}
          </span>
        </div>
        <div className="progress-bar-track" role="progressbar" aria-valuenow={coveragePct} aria-valuemin={0} aria-valuemax={100}>
          <div
            className="progress-bar-fill"
            style={{ width: `${coveragePct}%` }}
          />
        </div>
        <span className="goal-progress-disclaimer">
          {permittedPaise !== null
            ? `Initial savings coverage; remaining ₹${formatINR(goal.net_funding_gap_paise, { showPaise: false, prefix: '' })} to be funded via monthly savings.`
            : 'Savings allocation will be computed once savings and reserve are entered in your profile.'}
        </span>
      </div>

      {/* Capping Alert if applicable */}
      {goal.is_allocation_capped && (
        <div className="goal-capped-alert">
          <span>⚠️ Requested savings allocation was capped at {formatINR(goal.permitted_allocated_savings_paise)} to protect your emergency reserve.</span>
        </div>
      )}

      {/* 3 Metrics Row */}
      <div className="goal-metrics-row">
        <div className="goal-metric-col">
          <span className="goal-metric-value">
            {formatINR(goal.permitted_allocated_savings_paise, { fallback: 'Pending' })}
          </span>
          <span className="goal-metric-label">Allocated from savings</span>
        </div>
        <div className="goal-metric-col">
          <span className="goal-metric-value">
            {formatINR(goal.net_funding_gap_paise, { fallback: 'Pending' })}
          </span>
          <span className="goal-metric-label">Funding gap</span>
        </div>
        <div className="goal-metric-col">
          <span className="goal-metric-value">
            {feasibility?.required_monthly_savings_paise !== undefined &&
            feasibility.required_monthly_savings_paise !== null
              ? `${formatINR(feasibility.required_monthly_savings_paise)} / mo`
              : '—'}
          </span>
          <span className="goal-metric-label">Required savings</span>
        </div>
      </div>
    </div>
  );
};
