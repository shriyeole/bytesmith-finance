import React from 'react';

interface CurrencyInputProps {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  helperText?: string;
  error?: string | null;
  placeholder?: string;
  disabled?: boolean;
  required?: boolean;
}

export const CurrencyInput: React.FC<CurrencyInputProps> = ({
  id,
  label,
  value,
  onChange,
  helperText,
  error,
  placeholder = '0',
  disabled = false,
  required = false,
}) => {
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    // Pass raw string directly to parent to preserve empty vs explicit zero
    onChange(e.target.value);
  };

  return (
    <div className={`form-field ${error ? 'form-field--error' : ''}`}>
      <div className="form-field__label-row">
        <label htmlFor={id} className="form-field__label">
          {label}
          {required && <span className="form-field__required">*</span>}
        </label>
      </div>

      {helperText && (
        <p className="form-field__helper" id={`${id}-helper`}>
          {helperText}
        </p>
      )}

      <div className="currency-input-wrapper">
        <span className="currency-input-prefix" aria-hidden="true">
          ₹
        </span>
        <input
          id={id}
          type="text"
          inputMode="decimal"
          className="currency-input"
          value={value}
          onChange={handleChange}
          placeholder={placeholder}
          disabled={disabled}
          aria-describedby={helperText ? `${id}-helper` : undefined}
          aria-invalid={!!error}
        />
        {value !== '' && (
          <button
            type="button"
            className="currency-input-clear"
            onClick={() => onChange('')}
            title="Clear value"
            aria-label="Clear value"
            tabIndex={-1}
          >
            ×
          </button>
        )}
      </div>

      {error && (
        <p className="form-field__error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
};
