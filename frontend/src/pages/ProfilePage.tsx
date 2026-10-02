import React from 'react';
import { ProfileResponse } from '../api/types';
import { ProfileForm } from '../components/profile/ProfileForm';

interface ProfilePageProps {
  currentProfile: ProfileResponse | null;
  onProfileUpdated: (updatedProfile: ProfileResponse) => void;
  onNavigateToDashboard: () => void;
}

export const ProfilePage: React.FC<ProfilePageProps> = ({
  currentProfile,
  onProfileUpdated,
  onNavigateToDashboard,
}) => {
  return (
    <div className="page-container">
      <div className="page-header-row">
        <div>
          <button
            type="button"
            className="btn-back"
            onClick={onNavigateToDashboard}
          >
            ← Back to Dashboard
          </button>
          <h1 className="page-title">My Financial Profile</h1>
          <p className="page-subtitle">
            Manage your monthly cash flow baseline and protected emergency reserve.
          </p>
        </div>
      </div>

      <div className="page-content-grid">
        <div className="page-content-main">
          <ProfileForm
            currentProfile={currentProfile}
            onSuccess={(updated) => {
              onProfileUpdated(updated);
            }}
            onCancel={onNavigateToDashboard}
          />
        </div>

        <aside className="page-content-sidebar">
          <div className="card tip-card">
            <h3 className="tip-card__title">💡 Financial Profile Tips</h3>
            <ul className="tip-card__list">
              <li>
                <strong>Emergency Reserve Rule:</strong> Your reserve represents your essential safety net. The copilot ensures your reserve never exceeds your existing savings.
              </li>
              <li>
                <strong>Zero vs Empty:</strong> Entering <code>0</code> means you have zero expense in that category. Leaving a field blank means the information is unrecorded.
              </li>
              <li>
                <strong>Monthly Surplus:</strong> Take-Home Income minus (Fixed + Living + Discretionary) represents your monthly capacity to fund goals.
              </li>
            </ul>
          </div>
        </aside>
      </div>
    </div>
  );
};
