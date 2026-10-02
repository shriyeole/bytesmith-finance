/**
 * Safe currency utilities for ByteSmiths Personal Finance Copilot.
 * Avoids JavaScript floating-point errors by using integer paise and exact string operations.
 */

interface FormatOptions {
  showPaise?: boolean;
  fallback?: string;
  prefix?: string;
}

/**
 * Format an integer paise value into Indian Rupee format (e.g., "₹1,00,000" or "₹1,00,000.00").
 * Preserves null/undefined by returning the fallback string (never silently ₹0).
 */
export function formatINR(
  paise: number | null | undefined,
  options: FormatOptions = {}
): string {
  const { showPaise = false, fallback = '—', prefix = '₹' } = options;

  if (paise === null || paise === undefined) {
    return fallback;
  }

  const isNegative = paise < 0;
  const absPaise = Math.abs(paise);

  const rupees = Math.floor(absPaise / 100);
  const remainderPaise = absPaise % 100;

  // Use Indian number formatting for the integer rupee portion
  const formattedRupees = rupees.toLocaleString('en-IN');
  const sign = isNegative ? '-' : '';

  if (showPaise || remainderPaise > 0) {
    const paddedPaise = remainderPaise.toString().padStart(2, '0');
    return `${sign}${prefix}${formattedRupees}.${paddedPaise}`;
  }

  return `${sign}${prefix}${formattedRupees}`;
}

/**
 * Convert integer paise to a plain rupee string for pre-populating an input field.
 * e.g., 10000000 paise -> "100000" (or "100000.50" if paise exist).
 * Returns empty string for null/undefined.
 */
export function paiseToRupeeInputString(
  paise: number | null | undefined
): string {
  if (paise === null || paise === undefined) {
    return '';
  }

  const absPaise = Math.abs(paise);
  const rupees = Math.floor(absPaise / 100);
  const remainderPaise = absPaise % 100;
  const sign = paise < 0 ? '-' : '';

  if (remainderPaise === 0) {
    return `${sign}${rupees}`;
  }
  return `${sign}${rupees}.${remainderPaise.toString().padStart(2, '0')}`;
}

/**
 * Validate and clean a user-entered rupee string.
 * Strips commas and leading/trailing whitespace.
 * Returns null if the value is empty or whitespace.
 * Throws an Error if the value is not a valid non-negative rupee amount.
 */
export function cleanAndValidateRupeeInput(
  rawInput: string,
  fieldName = 'Amount'
): string | null {
  const trimmed = rawInput.trim();
  if (trimmed === '') {
    return null;
  }

  // Remove currency symbols, commas, and internal spaces
  const cleaned = trimmed.replace(/[₹,\s]/g, '');

  if (cleaned === '') {
    return null;
  }

  // Check valid non-negative decimal string pattern
  const decimalRegex = /^\d+(\.\d{1,2})?$/;
  if (!decimalRegex.test(cleaned)) {
    if (cleaned.startsWith('-')) {
      throw new Error(`${fieldName} cannot be negative.`);
    }
    if (cleaned.includes('.') && cleaned.split('.')[1].length > 2) {
      throw new Error(`${fieldName} cannot have more than 2 decimal places (paise precision).`);
    }
    throw new Error(`Please enter a valid numeric ${fieldName.toLowerCase()}.`);
  }

  return cleaned;
}
