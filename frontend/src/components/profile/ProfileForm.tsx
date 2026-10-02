import React, { useEffect, useState } from 'react';
import { api, ClientError } from '../../api/client';
import { ProfileResponse, ProfileUpdateRequest } from '../../api/types';
import {
  cleanAndValidateRupeeInput,
  paiseToRupeeInputString,
} from '../../utils/currency';
import { CurrencyInput } from '../common/CurrencyInput';
import { AlertCircleIcon, CheckCircleIcon, SpinnerIcon } from '../common/Icons';

interface ProfileFormProps {
  currentProfile: ProfileResponse | null;
  onSuccess: (updatedProfile: ProfileResponse) => void;
  onCancel?: () => void;
}

export const ProfileForm: React.FC<ProfileFormProps> = ({
  currentProfile,
  onSuccess,
  onCancel,
}) => {
  // Input string states (preserves user typing and empty vs zero)
  const [income, setIncome] = useState<string>('');
  const [savings, setSavings] = useState<string>('');
  const [reserve, setReserve] = useState<string>('');
  const [fixed, setFixed] = useState<string>('');
  const [living, setLiving] = useState<string>('');
  const [discretionary, setDiscretionary] = useState<string>('');

  // UI / Feedback states
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  // Initialize or re-populate when currentProfile changes
  useEffect(() => {
    if (currentProfile) {
      setIncome(paiseToRupeeInputString(currentProfile.monthly_take_home_income_paise));
      setSavings(paiseToRupeeInputString(currentProfile.existing_savings_paise));
      setReserve(paiseToRupeeInputString(currentProfile.emergency_reserve_paise));
      setFixed(paiseToRupeeInputString(currentProfile.monthly_fixed_commitments_paise));
      setLiving(paiseToRupeeInputString(currentProfile.monthly_estimated_living_expenses_paise));
      setDiscretionary(paiseToRupeeInputString(currentProfile.monthly_estimated_discretionary_paise));
    } else {
      setIncome('');
      setSavings('');
      setReserve('');
      setFixed('');
      setLiving('');
      setDiscretionary('');
    }
    setFieldErrors({});
    setFormError(null);
  }, [currentProfile]);

  // Live cross-field validation for Emergency Reserve <= Existing Savings
  useEffect(() => {
    try {
      const cleanSav = cleanAndValidateRupeeInput(savings, 'Existing savings');
      const cleanRes = cleanAndValidateRupeeInput(reserve, 'Emergency reserve');

      if (cleanSav !== null && cleanRes !== null) {
        // Compare using numeric values
        const savNum = parseFloat(cleanSav);
        const resNum = parseFloat(cleanRes);
        if (resNum > savNum) {
          setFieldErrors((prev) => ({
            ...prev,
            reserve: 'Emergency reserve cannot exceed existing savings.',
          }));
          return;
        }
      }
      // Clear cross-field error if valid
      setFieldErrors((prev) => {
        if (prev.reserve === 'Emergency reserve cannot exceed existing savings.') {
          const next = { ...prev };
          delete next.reserve;
          return next;
        }
        return prev;
      });
    } catch {
      // Individual field validation on submit handles malformed formats
    }
  }, [savings, reserve]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setSuccessMsg(null);
    const errors: Record<string, string> = {};

    let cleanIncome: string | null = null;
    let cleanSavings: string | null = null;
    let cleanReserve: string | null = null;
    let cleanFixed: string | null = null;
    let cleanLiving: string | null = null;
    let cleanDisc: string | null = null;

    try {
      cleanIncome = cleanAndValidateRupeeInput(income, 'Monthly take-home income');
    } catch (err: unknown) {
      errors.income = (err as Error).message;
    }

    try {
      cleanSavings = cleanAndValidateRupeeInput(savings, 'Existing savings');
    } catch (err: unknown) {
      errors.savings = (err as Error).message;
    }

    try {
      cleanReserve = cleanAndValidateRupeeInput(reserve, 'Emergency reserve');
    } catch (err: unknown) {
      errors.reserve = (err as Error).message;
    }

    try {
      cleanFixed = cleanAndValidateRupeeInput(fixed, 'Monthly fixed commitments');
    } catch (err: unknown) {
      errors.fixed = (err as Error).message;
    }

    try {
      cleanLiving = cleanAndValidateRupeeInput(living, 'Monthly living expenses');
    } catch (err: unknown) {
      errors.living = (err as Error).message;
    }

    try {
      cleanDisc = cleanAndValidateRupeeInput(discretionary, 'Monthly discretionary spending');
    } catch (err: unknown) {
      errors.discretionary = (err as Error).message;
    }

    // Cross-field check
    if (!errors.savings && !errors.reserve && cleanSavings !== null && cleanReserve !== null) {
      if (parseFloat(cleanReserve) > parseFloat(cleanSavings)) {
        errors.reserve = 'Emergency reserve cannot exceed existing savings.';
      }
    }

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      setFormError('Please resolve the errors highlighted below.');
      return;
    }

    setFieldErrors({});

    // Build payload preserving null versus zero versus omission semantics:
    // If input is trimmed empty string:
    // - If profile had a value, send null to clear it.
    // - If profile was null/empty, send null.
    // If input has a value, send the cleaned decimal string.
    const payload: ProfileUpdateRequest = {
      monthly_take_home_income: cleanIncome,
      existing_savings: cleanSavings,
      emergency_reserve: cleanReserve,
      monthly_fixed_commitments: cleanFixed,
      monthly_estimated_living_expenses: cleanLiving,
      monthly_estimated_discretionary: cleanDisc,
      currency: 'INR',
    };

    setIsSubmitting(true);
    try {
      const updated = await api.updateProfile(payload);
      setSuccessMsg('Financial profile saved successfully!');
      onSuccess(updated);
    } catch (err: unknown) {
      if (err instanceof ClientError) {
        setFormError(err.message);
      } else {
        setFormError((err as Error).message || 'Failed to save financial profile.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleReset = () => {
    if (currentProfile) {
      setIncome(paiseToRupeeInputString(currentProfile.monthly_take_home_income_paise));
      setSavings(paiseToRupeeInputString(currentProfile.existing_savings_paise));
      setReserve(paiseToRupeeInputString(currentProfile.emergency_reserve_paise));
      setFixed(paiseToRupeeInputString(currentProfile.monthly_fixed_commitments_paise));
      setLiving(paiseToRupeeInputString(currentProfile.monthly_estimated_living_expenses_paise));
      setDiscretionary(paiseToRupeeInputString(currentProfile.monthly_estimated_discretionary_paise));
    } else {
      setIncome('');
      setSavings('');
      setReserve('');
      setFixed('');
      setLiving('');
      setDiscretionary('');
    }
    setFieldErrors({});
    setFormError(null);
    setSuccessMsg(null);
  };

  return (
    <form className="profile-form card" onSubmit={handleSubmit} noValidate>
      <div className="card__header-row">
        <div>
          <h2 className="card__title">
            {currentProfile ? 'Edit Financial Profile' : 'Set Up Financial Profile'}
          </h2>
          <p className="card__subtitle">
            Enter your monthly cash flow, savings, and reserve to calculate your baseline surplus and goal feasibility.
          </p>
        </div>
      </div>

      {formError && (
        <div className="form-alert form-alert--error" role="alert">
          <AlertCircleIcon size={20} color="#DC2626" />
          <span>{formError}</span>
        </div>
      )}

      {successMsg && (
        <div className="form-alert form-alert--success" role="status">
          <CheckCircleIcon size={20} color="#16A34A" />
          <span>{successMsg}</span>
        </div>
      )}

      {/* Income Section */}
      <div className="form-section">
        <h3 className="form-section__heading">Monthly Income</h3>
        <p className="form-section__sub">
          Your regular take-home monthly salary or net business earnings after taxes.
        </p>
        <div className="form-grid form-grid--1">
          <CurrencyInput
            id="monthly_take_home_income"
            label="Monthly Take-Home Income"
            value={income}
            onChange={(val) => {
              setIncome(val);
              if (fieldErrors.income) {
                setFieldErrors((prev) => ({ ...prev, income: '' }));
              }
            }}
            placeholder="e.g. 1,00,000"
            helperText="Enter your monthly in-hand income. Must be strictly positive for profile completeness."
            error={fieldErrors.income}
          />
        </div>
      </div>

      {/* Savings & Reserve Section */}
      <div className="form-section">
        <h3 className="form-section__heading">Savings & Emergency Protection</h3>
        <p className="form-section__sub">
          The emergency reserve represents money you protect from goal allocation. Only savings above this reserve can be allocated to goals.
        </p>
        <div className="form-grid form-grid--2">
          <CurrencyInput
            id="existing_savings"
            label="Existing Total Savings"
            value={savings}
            onChange={(val) => {
              setSavings(val);
              if (fieldErrors.savings) {
                setFieldErrors((prev) => ({ ...prev, savings: '' }));
              }
            }}
            placeholder="e.g. 6,00,000"
            helperText="Total liquid funds in savings accounts and deposits."
            error={fieldErrors.savings}
          />

          <CurrencyInput
            id="emergency_reserve"
            label="Emergency Reserve (Protected)"
            value={reserve}
            onChange={(val) => {
              setReserve(val);
              if (fieldErrors.reserve) {
                setFieldErrors((prev) => ({ ...prev, reserve: '' }));
              }
            }}
            placeholder="e.g. 3,00,000"
            helperText="Amount protected for emergencies. Must not exceed existing savings."
            error={fieldErrors.reserve}
          />
        </div>
      </div>

      {/* Expenses Section */}
      <div className="form-section">
        <h3 className="form-section__heading">Monthly Expense Breakdown</h3>
        <p className="form-section__sub">
          Categorize your regular monthly outflows. Entering 0 is valid for categories you do not incur.
        </p>
        <div className="form-grid form-grid--3">
          <CurrencyInput
            id="monthly_fixed_commitments"
            label="Fixed Commitments"
            value={fixed}
            onChange={(val) => {
              setFixed(val);
              if (fieldErrors.fixed) {
                setFieldErrors((prev) => ({ ...prev, fixed: '' }));
              }
            }}
            placeholder="e.g. 10,000"
            helperText="EMIs, rent, insurance premiums, non-negotiable obligations."
            error={fieldErrors.fixed}
          />

          <CurrencyInput
            id="monthly_estimated_living_expenses"
            label="Living Expenses"
            value={living}
            onChange={(val) => {
              setLiving(val);
              if (fieldErrors.living) {
                setFieldErrors((prev) => ({ ...prev, living: '' }));
              }
            }}
            placeholder="e.g. 20,000"
            helperText="Groceries, utilities, fuel, healthcare, daily necessities."
            error={fieldErrors.living}
          />

          <CurrencyInput
            id="monthly_estimated_discretionary"
            label="Discretionary Spending"
            value={discretionary}
            onChange={(val) => {
              setDiscretionary(val);
              if (fieldErrors.discretionary) {
                setFieldErrors((prev) => ({ ...prev, discretionary: '' }));
              }
            }}
            placeholder="e.g. 20,000"
            helperText="Dining out, entertainment, shopping, leisure."
            error={fieldErrors.discretionary}
          />
        </div>
      </div>

      {/* Form Action Buttons */}
      <div className="form-actions-row">
        <button
          type="submit"
          className="btn btn--primary"
          disabled={isSubmitting}
        >
          {isSubmitting ? (
            <>
              <SpinnerIcon size={16} />
              <span>Saving Profile...</span>
            </>
          ) : (
            <span>Save Financial Profile</span>
          )}
        </button>

        <button
          type="button"
          className="btn btn--secondary"
          onClick={handleReset}
          disabled={isSubmitting}
        >
          Reset to Saved
        </button>

        {onCancel && (
          <button
            type="button"
            className="btn btn--outline"
            onClick={onCancel}
            disabled={isSubmitting}
          >
            Cancel
          </button>
        )}
      </div>
    </form>
  );
};
