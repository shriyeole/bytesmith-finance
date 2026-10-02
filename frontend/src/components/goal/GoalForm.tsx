import React, { useEffect, useState } from 'react';
import { api, ClientError } from '../../api/client';
import { GoalResponse, GoalUpdateRequest, ProfileResponse } from '../../api/types';
import {
  cleanAndValidateRupeeInput,
  formatINR,
  paiseToRupeeInputString,
} from '../../utils/currency';
import { getTodayISODate } from '../../utils/date';
import { CurrencyInput } from '../common/CurrencyInput';
import { AlertCircleIcon, CheckCircleIcon, InfoCircleIcon, SpinnerIcon } from '../common/Icons';

interface GoalFormProps {
  currentGoal: GoalResponse | null;
  profile: ProfileResponse | null;
  onSuccess: (updatedGoal: GoalResponse) => void;
  onCancel?: () => void;
}

export const GoalForm: React.FC<GoalFormProps> = ({
  currentGoal,
  profile,
  onSuccess,
  onCancel,
}) => {
  const [title, setTitle] = useState<string>('');
  const [targetAmount, setTargetAmount] = useState<string>('');
  const [targetDate, setTargetDate] = useState<string>('');
  const [requestedAllocation, setRequestedAllocation] = useState<string>('');

  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  useEffect(() => {
    if (currentGoal) {
      setTitle(currentGoal.title);
      setTargetAmount(paiseToRupeeInputString(currentGoal.target_amount_paise));
      setTargetDate(currentGoal.target_date);
      setRequestedAllocation(paiseToRupeeInputString(currentGoal.requested_allocated_savings_paise));
    } else {
      setTitle('');
      setTargetAmount('');
      setTargetDate('');
      setRequestedAllocation('0');
    }
    setFieldErrors({});
    setFormError(null);
  }, [currentGoal]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setSuccessMsg(null);
    const errors: Record<string, string> = {};

    const trimmedTitle = title.trim();
    if (!trimmedTitle) {
      errors.title = 'Goal title cannot be empty.';
    }

    let cleanTarget: string | null = null;
    try {
      cleanTarget = cleanAndValidateRupeeInput(targetAmount, 'Target amount');
      if (cleanTarget === null || parseFloat(cleanTarget) <= 0) {
        errors.targetAmount = 'Target amount must be strictly greater than zero.';
      }
    } catch (err: unknown) {
      errors.targetAmount = (err as Error).message;
    }

    if (!targetDate) {
      errors.targetDate = 'Please select a target deadline.';
    } else {
      const today = getTodayISODate();
      if (targetDate < today) {
        errors.targetDate = `Target deadline cannot be in the past (${targetDate} < today ${today}).`;
      }
    }

    let cleanAllocation: string | null = null;
    try {
      cleanAllocation = cleanAndValidateRupeeInput(requestedAllocation, 'Requested savings allocation');
      if (cleanAllocation === null) {
        cleanAllocation = '0.00';
      }
    } catch (err: unknown) {
      errors.requestedAllocation = (err as Error).message;
    }

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      setFormError('Please resolve the errors highlighted below.');
      return;
    }

    setFieldErrors({});

    const payload: GoalUpdateRequest = {
      title: trimmedTitle,
      target_date: targetDate,
      target_amount: cleanTarget!,
      requested_allocated_savings: cleanAllocation || '0.00',
    };

    setIsSubmitting(true);
    try {
      const updated = await api.updateGoal(payload);
      setSuccessMsg('Financial goal saved successfully!');
      onSuccess(updated);
    } catch (err: unknown) {
      if (err instanceof ClientError) {
        setFormError(err.message);
      } else {
        setFormError((err as Error).message || 'Failed to save financial goal.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleReset = () => {
    if (currentGoal) {
      setTitle(currentGoal.title);
      setTargetAmount(paiseToRupeeInputString(currentGoal.target_amount_paise));
      setTargetDate(currentGoal.target_date);
      setRequestedAllocation(paiseToRupeeInputString(currentGoal.requested_allocated_savings_paise));
    } else {
      setTitle('');
      setTargetAmount('');
      setTargetDate('');
      setRequestedAllocation('0');
    }
    setFieldErrors({});
    setFormError(null);
    setSuccessMsg(null);
  };

  return (
    <form className="goal-form card" onSubmit={handleSubmit} noValidate>
      <div className="card__header-row">
        <div>
          <h2 className="card__title">
            {currentGoal ? 'Edit Financial Goal' : 'Create Active Financial Goal'}
          </h2>
          <p className="card__subtitle">
            Configure your single active priority goal. We evaluate its feasibility against your monthly cash flow surplus.
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

      {/* Goal Details Section */}
      <div className="form-section">
        <h3 className="form-section__heading">Goal Overview</h3>
        <div className="form-grid form-grid--2">
          <div className={`form-field ${fieldErrors.title ? 'form-field--error' : ''}`}>
            <label htmlFor="goal_title" className="form-field__label">
              Goal Title <span className="form-field__required">*</span>
            </label>
            <input
              id="goal_title"
              type="text"
              className="text-input"
              value={title}
              onChange={(e) => {
                setTitle(e.target.value);
                if (fieldErrors.title) {
                  setFieldErrors((prev) => ({ ...prev, title: '' }));
                }
              }}
              placeholder="e.g. Buy a Car, Home Down Payment, Emergency Fund"
              required
            />
            {fieldErrors.title && <p className="form-field__error">{fieldErrors.title}</p>}
          </div>

          <CurrencyInput
            id="goal_target_amount"
            label="Target Amount"
            required
            value={targetAmount}
            onChange={(val) => {
              setTargetAmount(val);
              if (fieldErrors.targetAmount) {
                setFieldErrors((prev) => ({ ...prev, targetAmount: '' }));
              }
            }}
            placeholder="e.g. 7,00,000"
            helperText="Total monetary cost required for this goal."
            error={fieldErrors.targetAmount}
          />
        </div>

        <div className="form-grid form-grid--2 mt-3">
          <div className={`form-field ${fieldErrors.targetDate ? 'form-field--error' : ''}`}>
            <label htmlFor="goal_target_date" className="form-field__label">
              Target Deadline <span className="form-field__required">*</span>
            </label>
            <input
              id="goal_target_date"
              type="date"
              className="text-input"
              value={targetDate}
              min={getTodayISODate()}
              onChange={(e) => {
                setTargetDate(e.target.value);
                if (fieldErrors.targetDate) {
                  setFieldErrors((prev) => ({ ...prev, targetDate: '' }));
                }
              }}
              required
            />
            <p className="form-field__helper">
              The date you wish to achieve this goal. Must be today or in the future.
            </p>
            {fieldErrors.targetDate && <p className="form-field__error">{fieldErrors.targetDate}</p>}
          </div>

          <CurrencyInput
            id="goal_requested_allocation"
            label="Upfront Savings to Allocate"
            value={requestedAllocation}
            onChange={(val) => {
              setRequestedAllocation(val);
              if (fieldErrors.requestedAllocation) {
                setFieldErrors((prev) => ({ ...prev, requestedAllocation: '' }));
              }
            }}
            placeholder="0"
            helperText="Existing savings you want to put toward this goal immediately."
            error={fieldErrors.requestedAllocation}
          />
        </div>
      </div>

      {/* Emergency Reserve Capping Explanation */}
      <div className="callout-box callout-box--info">
        <div className="callout-box__icon">
          <InfoCircleIcon size={20} color="#2563EB" />
        </div>
        <div className="callout-box__content">
          <h4 className="callout-box__title">Emergency Reserve Protection Rule</h4>
          <p className="callout-box__text">
            To safeguard your financial stability, our backend strictly preserves your designated emergency reserve.
            The permitted upfront allocation is capped at your <strong>unencumbered savings</strong> (Existing Savings minus Emergency Reserve).
          </p>
          {profile && (
            <p className="callout-box__sub">
              Your profile currently has {formatINR(profile.existing_savings_paise, { fallback: 'an unverified amount of' })} in savings and {formatINR(profile.emergency_reserve_paise, { fallback: 'an unverified' })} in reserve, yielding{' '}
              <strong>{formatINR(profile.unencumbered_savings_paise)}</strong> of unencumbered savings eligible for goal allocation.
            </p>
          )}
        </div>
      </div>

      {/* Permitted Allocation Display (From Backend) */}
      {currentGoal && (
        <div className="callout-box callout-box--neutral">
          <div className="callout-box__content">
            <h4 className="callout-box__title">Persisted Backend Allocation</h4>
            <div className="persisted-allocation-metrics">
              <div className="persisted-allocation-item">
                <span className="persisted-allocation-item__label">Requested allocation:</span>
                <span className="persisted-allocation-item__value">
                  {formatINR(currentGoal.requested_allocated_savings_paise)}
                </span>
              </div>
              <div className="persisted-allocation-item">
                <span className="persisted-allocation-item__label">Permitted allocation:</span>
                <span className="persisted-allocation-item__value">
                  {formatINR(currentGoal.permitted_allocated_savings_paise, { fallback: 'Pending profile data' })}
                </span>
              </div>
              <div className="persisted-allocation-item">
                <span className="persisted-allocation-item__label">Net funding gap:</span>
                <span className="persisted-allocation-item__value">
                  {formatINR(currentGoal.net_funding_gap_paise, { fallback: 'Pending profile data' })}
                </span>
              </div>
              <div className="persisted-allocation-item">
                <span className="persisted-allocation-item__label">Capping status:</span>
                <span className="persisted-allocation-item__value">
                  {currentGoal.is_allocation_capped ? '⚠️ Capped by Reserve' : '✓ Uncapped'}
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="form-actions-row">
        <button
          type="submit"
          className="btn btn--primary"
          disabled={isSubmitting}
        >
          {isSubmitting ? (
            <>
              <SpinnerIcon size={16} />
              <span>Saving Goal...</span>
            </>
          ) : (
            <span>Save Financial Goal</span>
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
