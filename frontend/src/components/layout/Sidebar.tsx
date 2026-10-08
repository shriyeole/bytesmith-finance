import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { DashboardIcon, GoalIcon, LogoIcon, ProfileIcon, ReportsIcon } from '../common/Icons';
import { StatusBadge } from '../common/StatusBadge';

interface SidebarProps {
  onNavigate?: () => void;
  className?: string;
}

const item = ({ isActive }: { isActive: boolean }) => `sidebar__nav-item ${isActive ? 'sidebar__nav-item--active' : ''}`;

export const Sidebar: React.FC<SidebarProps> = ({ onNavigate, className = '' }) => {
  const { pathname } = useLocation();
  return (
  <aside className={`sidebar ${className}`} aria-label="Main navigation">
    <div className="sidebar__brand">
      <div className="sidebar__logo-wrap"><LogoIcon size={32} /></div>
      <div className="sidebar__brand-text">
        <span className="sidebar__brand-title">ByteSmiths</span>
        <span className="sidebar__brand-subtitle">Financial Planner</span>
      </div>
    </div>

    <nav className="sidebar__nav">
      <NavLink to="/overview" className={item} onClick={onNavigate}><DashboardIcon size={20} /><span>Overview</span></NavLink>
      <NavLink to="/setup/profile" className={({ isActive }) => item({ isActive: isActive || pathname.startsWith('/setup') })} onClick={onNavigate}><ProfileIcon size={20} /><span>My finances</span></NavLink>
      <NavLink to="/goal-check" className={item} onClick={onNavigate}><GoalIcon size={20} /><span>Goal check</span><StatusBadge status="Beta" variant="neutral" /></NavLink>
      <div className="sidebar__nav-divider" />
      <div className="sidebar__nav-item sidebar__nav-item--disabled" title="Coming in release 2" aria-disabled="true">
        <ReportsIcon size={20} /><span>Plan & goals</span><StatusBadge status="Soon" variant="soon" />
      </div>
    </nav>
  </aside>
  );
};
