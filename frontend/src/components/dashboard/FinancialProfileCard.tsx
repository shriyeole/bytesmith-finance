import React from 'react';
import { ProfileResponse } from '../../api/types';
import { formatINR } from '../../utils/currency';
import {
  CreditCardIcon,
  PencilIcon,
  PiggyBankIcon,
  WalletIcon,
} from '../common/Icons';

interface FinancialProfileCardProps {
  profile: ProfileResponse | null;
  onEditProfile: () => void;
}

export const FinancialProfileCard: React.FC<FinancialProfileCardProps> = ({
  profile,
  onEditProfile,
}) => {
  if (!profile) {
    return (
      <div className="card financial-profile-card">
        <div className="card__header-row">
          <div>
            <h2 className="card__title">Your Financial Profile</h2>
            <p className="card__subtitle">
              This information is used to analyze your financial goals.
            </p>
          </div>
          <button
            type="button"
            className="btn btn--primary btn--sm"
            onClick={onEditProfile}
          >
            Create Profile
          </button>
        </div>
        <div className="card-empty-state">
          <p>No financial profile configured yet. Click above to add your income, savings, and expenses.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="card financial-profile-card">
      <div className="card__header-row">
        <div>
          <h2 className="card__title">Your Financial Profile</h2>
          <p className="card__subtitle">
            This information is used to analyze your financial goals.
          </p>
        </div>
        <button
          type="button"
          className="btn btn--primary btn--sm"
          onClick={onEditProfile}
          aria-label="Edit Financial Profile"
        >
          <PencilIcon size={14} />
          <span>Edit</span>
        </button>
      </div>

      {/* Income Section */}
      <div className="profile-section">
        <div className="profile-section__title-row">
          <WalletIcon size={18} color="#2563EB" />
          <h3 className="profile-section__title">Income</h3>
        </div>
        <div className="profile-boxes-grid profile-boxes-grid--1">
          <div className="profile-mini-box">
            <span className="profile-mini-box__label">Monthly take-home income</span>
            <span className="profile-mini-box__value">
              {formatINR(profile.monthly_take_home_income_paise, { fallback: 'Not set' })}
            </span>
          </div>
        </div>
      </div>

      {/* Savings & Emergency Reserve Section */}
      <div className="profile-section">
        <div className="profile-section__title-row">
          <PiggyBankIcon size={18} color="#2563EB" />
          <h3 className="profile-section__title">Savings & Emergency Reserve</h3>
        </div>
        <div className="profile-boxes-grid profile-boxes-grid--2">
          <div className="profile-mini-box">
            <span className="profile-mini-box__label">Existing savings</span>
            <span className="profile-mini-box__value">
              {formatINR(profile.existing_savings_paise, { fallback: 'Not set' })}
            </span>
          </div>
          <div className="profile-mini-box">
            <span className="profile-mini-box__label">Emergency reserve</span>
            <span className="profile-mini-box__value">
              {formatINR(profile.emergency_reserve_paise, { fallback: 'Not set' })}
            </span>
          </div>
        </div>
        {profile.existing_savings_paise !== null && profile.emergency_reserve_paise !== null && (
          <div className="profile-section__note">
            Unencumbered savings (available for goals):{' '}
            <strong>{formatINR(profile.unencumbered_savings_paise)}</strong>
          </div>
        )}
      </div>

      {/* Monthly Expenses Section */}
      <div className="profile-section">
        <div className="profile-section__title-row">
          <CreditCardIcon size={18} color="#2563EB" />
          <h3 className="profile-section__title">Monthly Expenses</h3>
        </div>
        <div className="profile-boxes-grid profile-boxes-grid--3">
          <div className="profile-mini-box">
            <span className="profile-mini-box__label">Fixed commitments</span>
            <span className="profile-mini-box__value">
              {formatINR(profile.monthly_fixed_commitments_paise, { fallback: 'Not set' })}
            </span>
          </div>
          <div className="profile-mini-box">
            <span className="profile-mini-box__label">Living expenses</span>
            <span className="profile-mini-box__value">
              {formatINR(profile.monthly_estimated_living_expenses_paise, { fallback: 'Not set' })}
            </span>
          </div>
          <div className="profile-mini-box">
            <span className="profile-mini-box__label">Discretionary spending</span>
            <span className="profile-mini-box__value">
              {formatINR(profile.monthly_estimated_discretionary_paise, { fallback: 'Not set' })}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
