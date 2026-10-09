import React from 'react';
import { Link } from 'react-router-dom';
import { useAlerts } from '../../api/journey';
import { useAuth } from '../../auth/AuthContext';

export const TopHeader: React.FC<{ className?: string }> = ({ className = '' }) => {
  const { user, mode } = useAuth();
  const name = user?.displayName || user?.email || user?.uid || '';
  const alerts = useAlerts(false);
  const urgent = (alerts.data?.counts.critical ?? 0) + (alerts.data?.counts.warning ?? 0);
  const total = alerts.data?.alerts.length ?? 0;
  return (
    <header className={`top-header ${className}`} role="banner">
      <div className="top-header__spacer" />
      {mode === 'dev' && <span className="status-badge status-badge--neutral">Dev login</span>}
      <Link to="/alerts" className="bell" aria-label={`Alerts: ${total} open${urgent ? `, ${urgent} important` : ''}`}>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.7 21a2 2 0 0 1-3.4 0" /></svg>
        {total > 0 && <span className={`bell__count ${urgent ? 'bell__count--urgent' : ''}`}>{total}</span>}
      </Link>
      <Link to="/account" className="top-header__user-menu" aria-label="Account settings">
        <div className="top-header__avatar" aria-hidden="true">{name.charAt(0).toUpperCase()}</div>
        <span className="top-header__username">{name}</span>
      </Link>
    </header>
  );
};
