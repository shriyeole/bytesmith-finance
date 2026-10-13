import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { useFeatures } from '../../api/plan';
import { DashboardIcon, GoalIcon, LogoIcon, ProfileIcon, ReportsIcon } from '../common/Icons';

interface SidebarProps {
  onNavigate?: () => void;
  className?: string;
}

const ShieldIcon: React.FC = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
  </svg>
);

const Svg: React.FC<{ d: string }> = ({ d }) => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={d} /></svg>
);
const BudgetIcon = () => <Svg d="M3 6h18M3 12h12M3 18h7" />;
const MixIcon = () => <Svg d="M12 3a9 9 0 1 0 9 9h-9z M14 2.5V10h7.5A8 8 0 0 0 14 2.5z" />;
const HistoryIcon = () => <Svg d="M3 12a9 9 0 1 0 3-6.7L3 8 M3 3v5h5 M12 7v5l3 2" />;
const ChatIcon = () => <Svg d="M4 5h16v11H9l-5 4z M8 9h8 M8 12h5" />;

const item = ({ isActive }: { isActive: boolean }) => `sidebar__nav-item ${isActive ? 'sidebar__nav-item--active' : ''}`;

export const Sidebar: React.FC<SidebarProps> = ({ onNavigate, className = '' }) => {
  const { pathname } = useLocation();
  const features = useFeatures();
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
      <NavLink to="/start" className={item} onClick={onNavigate}><ChatIcon /><span>Setup chat</span></NavLink>
      <NavLink to="/setup/profile" className={({ isActive }) => item({ isActive: isActive || pathname.startsWith('/setup') })} onClick={onNavigate}><ProfileIcon size={20} /><span>My finances</span></NavLink>
      <NavLink to="/goals" className={item} onClick={onNavigate}><GoalIcon size={20} /><span>Goals</span></NavLink>
      <NavLink to="/budget" className={item} onClick={onNavigate}><BudgetIcon /><span>Budget</span></NavLink>
      {features.data?.allocation && <NavLink to="/investing" className={item} onClick={onNavigate}><MixIcon /><span>Investing mix</span></NavLink>}
      <NavLink to="/safety" className={item} onClick={onNavigate}><ShieldIcon /><span>Safety net</span></NavLink>
      <NavLink to="/plan" className={item} onClick={onNavigate}><HistoryIcon /><span>Plan & history</span></NavLink>
      <NavLink to="/journey" className={item} onClick={onNavigate}><ReportsIcon size={20} /><span>Wealth journey</span></NavLink>
    </nav>
  </aside>
  );
};
