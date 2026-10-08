import React from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';

export const TopHeader: React.FC<{ className?: string }> = ({ className = '' }) => {
  const { user, mode } = useAuth();
  const name = user?.displayName || user?.email || user?.uid || '';
  return (
    <header className={`top-header ${className}`} role="banner">
      <div className="top-header__spacer" />
      {mode === 'dev' && <span className="status-badge status-badge--neutral">Dev login</span>}
      <Link to="/account" className="top-header__user-menu" aria-label="Account settings">
        <div className="top-header__avatar" aria-hidden="true">{name.charAt(0).toUpperCase()}</div>
        <span className="top-header__username">{name}</span>
      </Link>
    </header>
  );
};
