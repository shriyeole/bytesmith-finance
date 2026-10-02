import React from 'react';

export type BadgeVariant =
  | 'active'
  | 'feasible'
  | 'stretch'
  | 'infeasible'
  | 'insufficient'
  | 'soon'
  | 'neutral';

interface StatusBadgeProps {
  status: string;
  variant?: BadgeVariant;
  className?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({
  status,
  variant,
  className = '',
}) => {
  // Infer variant from status string if not explicitly passed
  let resolvedVariant: BadgeVariant = variant || 'neutral';
  let label = status;

  if (!variant) {
    const s = status.toUpperCase();
    if (s === 'ACTIVE') {
      resolvedVariant = 'active';
      label = 'ACTIVE';
    } else if (s === 'FEASIBLE') {
      resolvedVariant = 'feasible';
      label = 'FEASIBLE';
    } else if (s === 'STRETCH_FEASIBLE') {
      resolvedVariant = 'stretch';
      label = 'STRETCH FEASIBLE';
    } else if (s === 'INFEASIBLE') {
      resolvedVariant = 'infeasible';
      label = 'INFEASIBLE';
    } else if (s === 'INSUFFICIENT_DATA') {
      resolvedVariant = 'insufficient';
      label = 'INSUFFICIENT DATA';
    } else if (s === 'SOON') {
      resolvedVariant = 'soon';
      label = 'Soon';
    }
  }

  return (
    <span className={`status-badge status-badge--${resolvedVariant} ${className}`}>
      {label}
    </span>
  );
};
