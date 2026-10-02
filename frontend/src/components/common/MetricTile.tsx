import React from 'react';

interface MetricTileProps {
  icon?: React.ReactNode;
  label: string;
  value: string | number;
  unit?: string;
  subtitle?: string;
  variant?: 'default' | 'highlight' | 'warning' | 'danger';
  className?: string;
}

export const MetricTile: React.FC<MetricTileProps> = ({
  icon,
  label,
  value,
  unit,
  subtitle,
  variant = 'default',
  className = '',
}) => {
  return (
    <div className={`metric-tile metric-tile--${variant} ${className}`}>
      {icon && <div className="metric-tile__icon">{icon}</div>}
      <div className="metric-tile__content">
        <span className="metric-tile__label">{label}</span>
        <div className="metric-tile__value-row">
          <span className="metric-tile__value">{value}</span>
          {unit && <span className="metric-tile__unit">{unit}</span>}
        </div>
        {subtitle && <span className="metric-tile__subtitle">{subtitle}</span>}
      </div>
    </div>
  );
};
