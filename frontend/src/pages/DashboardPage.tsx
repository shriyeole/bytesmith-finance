import React from 'react';
import {
  GoalFeasibilityResponse,
  GoalResponse,
  ProfileResponse,
} from '../api/types';
import { CurrentGoalCard } from '../components/dashboard/CurrentGoalCard';
import { FeasibilityAnalysisCard } from '../components/dashboard/FeasibilityAnalysisCard';
import { FinancialProfileCard } from '../components/dashboard/FinancialProfileCard';
import { ProfileStatusCard } from '../components/dashboard/ProfileStatusCard';

interface DashboardPageProps {
  profile: ProfileResponse | null;
  goal: GoalResponse | null;
  feasibility: GoalFeasibilityResponse | null;
  onNavigateToProfile: () => void;
  onNavigateToGoal: () => void;
}

export const DashboardPage: React.FC<DashboardPageProps> = ({
  profile,
  goal,
  feasibility,
  onNavigateToProfile,
  onNavigateToGoal,
}) => {
  return (
    <div className="dashboard-page">
      {/* Welcome Header */}
      <section className="dashboard-welcome">
        <h1 className="dashboard-welcome__title">Welcome back!</h1>
        <p className="dashboard-welcome__subtitle">
          Get a clear view of your finances and work towards your goals.
        </p>
      </section>

      {/* Main 2-Column Responsive Grid */}
      <div className="dashboard-grid">
        {/* Left Column: Profile Status & Financial Profile */}
        <div className="dashboard-col">
          <ProfileStatusCard
            profile={profile}
            onEditProfile={onNavigateToProfile}
          />

          <FinancialProfileCard
            profile={profile}
            onEditProfile={onNavigateToProfile}
          />
        </div>

        {/* Right Column: Current Goal & Feasibility Analysis */}
        <div className="dashboard-col">
          <CurrentGoalCard
            goal={goal}
            feasibility={feasibility}
            onEditGoal={onNavigateToGoal}
          />

          <FeasibilityAnalysisCard
            feasibility={feasibility}
            onGoToProfile={onNavigateToProfile}
            onGoToGoal={onNavigateToGoal}
          />
        </div>
      </div>
    </div>
  );
};
