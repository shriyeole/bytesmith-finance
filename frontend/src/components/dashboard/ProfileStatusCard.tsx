import React from 'react';
import { ProfileResponse } from '../../api/types';
import { AlertCircleIcon, CheckCircleIcon, InfoCircleIcon } from '../common/Icons';

interface ProfileStatusCardProps {
  profile: ProfileResponse | null;
  onEditProfile: () => void;
}

export const ProfileStatusCard: React.FC<ProfileStatusCardProps> = ({
  profile,
  onEditProfile,
}) => {
  if (!profile) {
    return (
      <div className="card profile-status-card">
        <h2 className="card__title">Profile Status</h2>
        <div className="profile-status-banner profile-status-banner--neutral">
          <div className="profile-status-banner__icon">
            <InfoCircleIcon size={32} color="#2563EB" />
          </div>
          <div className="profile-status-banner__body">
            <h3 className="profile-status-banner__title profile-status-banner__title--neutral">
              No Profile Configured
            </h3>
            <p className="profile-status-banner__desc">
              Create your financial profile with income, savings, and expenses to start analyzing your goals.
            </p>
          </div>
          <button
            type="button"
            className="btn btn--outline"
            onClick={onEditProfile}
          >
            Set Up Profile
          </button>
        </div>
      </div>
    );
  }

  const isComplete = profile.is_complete;
  const missingCount = profile.missing_fields?.length || 0;

  return (
    <div className="card profile-status-card">
      <h2 className="card__title">Profile Status</h2>
      <div
        className={`profile-status-banner ${
          isComplete ? 'profile-status-banner--success' : 'profile-status-banner--warning'
        }`}
      >
        <div className="profile-status-banner__icon">
          {isComplete ? (
            <CheckCircleIcon size={32} color="#16A34A" />
          ) : (
            <AlertCircleIcon size={32} color="#D97706" />
          )}
        </div>
        <div className="profile-status-banner__body">
          <h3
            className={`profile-status-banner__title ${
              isComplete
                ? 'profile-status-banner__title--success'
                : 'profile-status-banner__title--warning'
            }`}
          >
            {isComplete ? 'Profile Complete' : 'Profile Incomplete'}
          </h3>
          <p className="profile-status-banner__desc">
            {isComplete
              ? 'All required information is set. You can create and analyze financial goals.'
              : `${missingCount} required field${missingCount === 1 ? '' : 's'} missing. Complete your profile to evaluate goal feasibility.`}
          </p>
        </div>
        <button
          type="button"
          className="btn btn--outline"
          onClick={onEditProfile}
        >
          {isComplete ? 'Edit Profile' : 'Complete Profile'}
        </button>
      </div>
    </div>
  );
};
