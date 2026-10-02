import React from 'react';
import { GoalResponse, ProfileResponse } from '../api/types';
import { GoalForm } from '../components/goal/GoalForm';

interface GoalPageProps {
  currentGoal: GoalResponse | null;
  profile: ProfileResponse | null;
  onGoalUpdated: (updatedGoal: GoalResponse) => void;
  onNavigateToDashboard: () => void;
}

export const GoalPage: React.FC<GoalPageProps> = ({
  currentGoal,
  profile,
  onGoalUpdated,
  onNavigateToDashboard,
}) => {
  return (
    <div className="page-container">
      <div className="page-header-row">
        <div>
          <button
            type="button"
            className="btn-back"
            onClick={onNavigateToDashboard}
          >
            ← Back to Dashboard
          </button>
          <h1 className="page-title">Financial Goal</h1>
          <p className="page-subtitle">
            Configure your priority financial target, timeline, and upfront savings allocation.
          </p>
        </div>
      </div>

      <div className="page-content-grid">
        <div className="page-content-main">
          <GoalForm
            currentGoal={currentGoal}
            profile={profile}
            onSuccess={(updated) => {
              onGoalUpdated(updated);
            }}
            onCancel={onNavigateToDashboard}
          />
        </div>

        <aside className="page-content-sidebar">
          <div className="card tip-card">
            <h3 className="tip-card__title">🎯 Goal Feasibility Guidance</h3>
            <ul className="tip-card__list">
              <li>
                <strong>Calendar Month Cycles:</strong> Savings cycles are calculated strictly based on calendar months. The current calendar month is treated as underway and not counted as a future cycle.
              </li>
              <li>
                <strong>Funding Gap:</strong> Target Amount minus permitted upfront savings allocation. This is the net balance you need to accumulate through monthly savings.
              </li>
              <li>
                <strong>Feasibility Tiers:</strong>
                <br />• <em>Feasible:</em> Monthly savings $\le$ Surplus.
                <br />• <em>Stretch:</em> Monthly savings $\le$ Surplus + Discretionary.
                <br />• <em>Infeasible:</em> Shortfall exceeds discretionary spending capacity.
              </li>
            </ul>
          </div>
        </aside>
      </div>
    </div>
  );
};
