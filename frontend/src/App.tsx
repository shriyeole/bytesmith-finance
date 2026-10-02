import React, { useCallback, useEffect, useState } from 'react';
import { api, ClientError } from './api/client';
import {
  GoalFeasibilityResponse,
  GoalResponse,
  ProfileResponse,
} from './api/types';
import { AlertCircleIcon, SpinnerIcon } from './components/common/Icons';
import { AppLayout } from './components/layout/AppLayout';
import { NavTab } from './components/layout/Sidebar';
import { DashboardPage } from './pages/DashboardPage';
import { GoalPage } from './pages/GoalPage';
import { ProfilePage } from './pages/ProfilePage';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<NavTab>('dashboard');

  // Core Financial Data State (from real backend responses)
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [goal, setGoal] = useState<GoalResponse | null>(null);
  const [feasibility, setFeasibility] = useState<GoalFeasibilityResponse | null>(null);

  // Loading & Global Communication
  const [loading, setLoading] = useState<boolean>(true);
  const [globalError, setGlobalError] = useState<string | null>(null);

  // Central Data Fetcher
  const refreshAllData = useCallback(async () => {
    setGlobalError(null);
    try {
      // 1. Fetch Profile and Goal in parallel
      const [fetchedProfile, fetchedGoal] = await Promise.all([
        api.getProfile(),
        api.getGoal(),
      ]);

      setProfile(fetchedProfile);
      setGoal(fetchedGoal);

      // 2. Fetch Feasibility if both or either exists (backend handles 404 if missing)
      if (fetchedProfile && fetchedGoal) {
        const fetchedFeasibility = await api.getFeasibility();
        setFeasibility(fetchedFeasibility);
      } else {
        setFeasibility(null);
      }
    } catch (err: unknown) {
      if (err instanceof ClientError) {
        // Status 0 represents connection failure to backend
        setGlobalError(err.message);
      } else {
        setGlobalError((err as Error).message || 'Failed to load financial data.');
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshAllData();
  }, [refreshAllData]);

  // Profile update handler: refreshes profile, then resyncs goal & feasibility
  const handleProfileUpdated = async (updatedProfile: ProfileResponse) => {
    setProfile(updatedProfile);
    try {
      // Profile changes can alter goal's permitted allocation capping & feasibility
      const [updatedGoal, updatedFeas] = await Promise.all([
        api.getGoal(),
        api.getFeasibility(),
      ]);
      setGoal(updatedGoal);
      setFeasibility(updatedFeas);
    } catch {
      // Silently fall back to refreshAllData
      refreshAllData();
    }
  };

  // Goal update handler: refreshes goal, then resyncs feasibility
  const handleGoalUpdated = async (updatedGoal: GoalResponse) => {
    setGoal(updatedGoal);
    try {
      const updatedFeas = await api.getFeasibility();
      setFeasibility(updatedFeas);
    } catch {
      refreshAllData();
    }
  };

  return (
    <AppLayout activeTab={activeTab} onSelectTab={setActiveTab}>
      {/* Global Connection / Fetch Error */}
      {globalError && (
        <div className="global-error-banner" role="alert">
          <AlertCircleIcon size={20} color="#DC2626" />
          <div style={{ flex: 1 }}>
            <strong>Connection Error:</strong> {globalError}
          </div>
          <button
            type="button"
            className="btn btn--outline btn--sm"
            onClick={refreshAllData}
          >
            Retry
          </button>
        </div>
      )}

      {/* Global Initial Loading Indicator */}
      {loading && !profile && !goal && !globalError && (
        <div className="global-loading-banner" role="status">
          <SpinnerIcon size={18} color="#2563EB" />
          <span>Connecting to ByteSmiths engine and loading financial data...</span>
        </div>
      )}

      {/* Active Tab View */}
      {activeTab === 'dashboard' && (
        <DashboardPage
          profile={profile}
          goal={goal}
          feasibility={feasibility}
          onNavigateToProfile={() => setActiveTab('profile')}
          onNavigateToGoal={() => setActiveTab('goal')}
        />
      )}

      {activeTab === 'profile' && (
        <ProfilePage
          currentProfile={profile}
          onProfileUpdated={(updated) => {
            handleProfileUpdated(updated);
          }}
          onNavigateToDashboard={() => setActiveTab('dashboard')}
        />
      )}

      {activeTab === 'goal' && (
        <GoalPage
          currentGoal={goal}
          profile={profile}
          onGoalUpdated={(updated) => {
            handleGoalUpdated(updated);
          }}
          onNavigateToDashboard={() => setActiveTab('dashboard')}
        />
      )}
    </AppLayout>
  );
};

export default App;
