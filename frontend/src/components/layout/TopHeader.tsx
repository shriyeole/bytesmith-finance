import React from 'react';

interface TopHeaderProps {
  userName?: string;
  className?: string;
}

export const TopHeader: React.FC<TopHeaderProps> = ({
  userName = 'user_default',
  className = '',
}) => {
  return (
    <header className={`top-header ${className}`} role="banner">
      <div className="top-header__spacer" />
      <div className="top-header__user-menu">
        <div className="top-header__avatar" aria-hidden="true">
          {userName.charAt(0).toUpperCase()}
        </div>
        <span className="top-header__username">{userName}</span>
        <svg
          className="top-header__chevron"
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </div>
    </header>
  );
};
