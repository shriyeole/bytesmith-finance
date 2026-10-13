import React, { useEffect } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import { useOnboarding } from './api/financialState';
import { ClientError, setTokenGetter } from './api/http';
import { AuthProvider, useAuth } from './auth/AuthContext';
import { SpinnerIcon } from './components/common/Icons';
import { AppLayout } from './components/layout/AppLayout';
import { AlertsPage } from './pages/AlertsPage';
import { BudgetPage } from './pages/BudgetPage';
import { GoalCheckPage } from './pages/GoalCheckPage';
import { GoalDetailPage } from './pages/GoalDetailPage';
import { GoalEditorPage } from './pages/GoalEditorPage';
import { GoalsPage } from './pages/GoalsPage';
import { InvestingPage } from './pages/InvestingPage';
import { JourneyPage } from './pages/JourneyPage';
import { LoginPage } from './pages/LoginPage';
import { OnboardingPage } from './pages/OnboardingPage';
import { OverviewPage } from './pages/OverviewPage';
import { PlanPage } from './pages/PlanPage';
import { SafetyPage } from './pages/SafetyPage';
import { SettingsPage } from './pages/SettingsPage';
import { StartPage } from './pages/StartPage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: (count, err) => !(err instanceof ClientError && err.status >= 400 && err.status < 500) && count < 2,
    },
  },
});

const Loading: React.FC = () => (
  <div className="global-loading-banner" role="status"><SpinnerIcon size={18} /><span>Loading…</span></div>
);

/** Gate: signed in, and the API client knows how to fetch the user's token. */
const RequireAuth: React.FC = () => {
  const auth = useAuth();
  const location = useLocation();
  useEffect(() => setTokenGetter(auth.getToken), [auth.getToken]);
  if (!auth.ready) return <Loading />;
  if (!auth.user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  setTokenGetter(auth.getToken); // set synchronously before children fetch
  return (
    <AppLayout>
      <Outlet />
    </AppLayout>
  );
};

/** "/" sends new users into setup and returning users to their overview. */
const Home: React.FC = () => {
  const ob = useOnboarding();
  if (ob.isLoading) return <Loading />;
  // New users start with the AI setup chat; the forms stay one click away.
  if (ob.data && ob.data.completed_count === 0) return <Navigate to="/start" replace />;
  return <Navigate to="/overview" replace />;
};

const App: React.FC = () => (
  <QueryClientProvider client={queryClient}>
    <AuthProvider>
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<RequireAuth />}>
            <Route index element={<Home />} />
            <Route path="overview" element={<OverviewPage />} />
            <Route path="start" element={<StartPage />} />
            <Route path="setup" element={<Navigate to="/setup/profile" replace />} />
            <Route path="setup/:step" element={<OnboardingPage />} />
            <Route path="goals" element={<GoalsPage />} />
            <Route path="goals/new" element={<GoalEditorPage />} />
            <Route path="goals/:id" element={<GoalDetailPage />} />
            <Route path="goals/:id/edit" element={<GoalEditorPage />} />
            <Route path="safety" element={<SafetyPage />} />
            <Route path="budget" element={<BudgetPage />} />
            <Route path="investing" element={<InvestingPage />} />
            <Route path="plan" element={<PlanPage />} />
            <Route path="journey" element={<JourneyPage />} />
            <Route path="alerts" element={<AlertsPage />} />
            {/* Original single-goal prototype; superseded by /goals, kept until removed. */}
            <Route path="goal-check" element={<GoalCheckPage />} />
            <Route path="account" element={<SettingsPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  </QueryClientProvider>
);

export default App;
