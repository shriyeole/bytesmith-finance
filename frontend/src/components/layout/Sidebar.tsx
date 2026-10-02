import React from 'react';
import {
  DashboardIcon,
  GoalIcon,
  LogoIcon,
  ProfileIcon,
  ReportsIcon,
  TransactionsIcon,
} from '../common/Icons';
import { StatusBadge } from '../common/StatusBadge';

export type NavTab = 'dashboard' | 'profile' | 'goal';

interface SidebarProps {
  activeTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
  className?: string;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  onSelectTab,
  className = '',
}) => {
  return (
    <aside className={`sidebar ${className}`} aria-label="Main Navigation">
      <div className="sidebar__brand">
        <div className="sidebar__logo-wrap">
          <LogoIcon size={32} />
        </div>
        <div className="sidebar__brand-text">
          <span className="sidebar__brand-title">ByteSmiths</span>
          <span className="sidebar__brand-subtitle">Finance Copilot</span>
        </div>
      </div>

      <nav className="sidebar__nav">
        <button
          type="button"
          className={`sidebar__nav-item ${activeTab === 'dashboard' ? 'sidebar__nav-item--active' : ''}`}
          onClick={() => onSelectTab('dashboard')}
          aria-current={activeTab === 'dashboard' ? 'page' : undefined}
        >
          <DashboardIcon size={20} />
          <span>Dashboard</span>
        </button>

        <button
          type="button"
          className={`sidebar__nav-item ${activeTab === 'profile' ? 'sidebar__nav-item--active' : ''}`}
          onClick={() => onSelectTab('profile')}
          aria-current={activeTab === 'profile' ? 'page' : undefined}
        >
          <ProfileIcon size={20} />
          <span>My Profile</span>
        </button>

        <button
          type="button"
          className={`sidebar__nav-item ${activeTab === 'goal' ? 'sidebar__nav-item--active' : ''}`}
          onClick={() => onSelectTab('goal')}
          aria-current={activeTab === 'goal' ? 'page' : undefined}
        >
          <GoalIcon size={20} />
          <span>Financial Goal</span>
        </button>

        <div className="sidebar__nav-divider" />

        <div
          className="sidebar__nav-item sidebar__nav-item--disabled"
          title="Coming soon in a future release"
          aria-disabled="true"
        >
          <TransactionsIcon size={20} />
          <span>Transactions</span>
          <StatusBadge status="Soon" variant="soon" />
        </div>

        <div
          className="sidebar__nav-item sidebar__nav-item--disabled"
          title="Coming soon in a future release"
          aria-disabled="true"
        >
          <ReportsIcon size={20} />
          <span>Reports</span>
          <StatusBadge status="Soon" variant="soon" />
        </div>
      </nav>
    </aside>
  );
};
