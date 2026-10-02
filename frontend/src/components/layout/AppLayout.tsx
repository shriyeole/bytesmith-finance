import React, { useState } from 'react';
import { NavTab, Sidebar } from './Sidebar';
import { TopHeader } from './TopHeader';

interface AppLayoutProps {
  activeTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
  children: React.ReactNode;
}

export const AppLayout: React.FC<AppLayoutProps> = ({
  activeTab,
  onSelectTab,
  children,
}) => {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <div className="app-shell">
      {/* Mobile Header Bar */}
      <div className="mobile-header">
        <button
          type="button"
          className="mobile-header__menu-btn"
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          aria-label="Toggle navigation menu"
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="3" y1="12" x2="21" y2="12" />
            <line x1="3" y1="6" x2="21" y2="6" />
            <line x1="3" y1="18" x2="21" y2="18" />
          </svg>
        </button>
        <span className="mobile-header__title">ByteSmiths</span>
      </div>

      {/* Sidebar (Desktop and Mobile Drawer) */}
      <div className={`sidebar-container ${mobileMenuOpen ? 'sidebar-container--open' : ''}`}>
        <Sidebar
          activeTab={activeTab}
          onSelectTab={(tab) => {
            onSelectTab(tab);
            setMobileMenuOpen(false);
          }}
        />
        {mobileMenuOpen && (
          <div
            className="sidebar-backdrop"
            onClick={() => setMobileMenuOpen(false)}
            aria-hidden="true"
          />
        )}
      </div>

      {/* Main Content Area */}
      <div className="main-content-wrapper">
        <TopHeader />
        <main className="main-viewport">{children}</main>
      </div>
    </div>
  );
};
