"""Pure financial money utilities for ByteSmiths Finance Copilot.

Enforces integer paise precision, Indian numbering system formatting,
and ceiling division for monthly goal savings calculations.
"""

from decimal import Decimal
import re
from typing import Union

_DECIMAL_STRING_PATTERN = re.compile(r"^(0|[1-9]\d*)(\.\d{1,2})?$")


def rupees_to_paise(amount: Union[str, Decimal]) -> int:
    """Convert a non-negative rupee amount to integer paise.

    Args:
        amount: Decimal string (e.g. "1234", "1234.5", "1234.56") with up to 2 decimal places,
                or a Decimal instance that resolves exactly to an integer number of paise
                (e.g. Decimal("0.10"), Decimal("1.230")).

    Returns:
        Integer paise (1 Rupee = 100 Paise).

    Raises:
        TypeError: If input is not a str or Decimal (e.g. float, bool, int).
        ValueError: If amount is negative, malformed, non-finite (NaN/Inf),
                    contains more than two decimal places (for str), or does
                    not resolve to an integer number of paise (for Decimal).
    """
    if isinstance(amount, bool) or not isinstance(amount, (str, Decimal)):
        raise TypeError(
            f"Amount must be a decimal string or Decimal instance, got {type(amount).__name__}"
        )

    if isinstance(amount, str):
        if amount.startswith("-"):
            raise ValueError(f"Rupee amount cannot be negative: '{amount}'")
        if not _DECIMAL_STRING_PATTERN.match(amount):
            if "." in amount and len(amount.split(".")[1]) > 2:
                raise ValueError(
                    f"Rupee amount cannot have more than two decimal places: '{amount}'"
                )
            raise ValueError(f"Malformed rupee decimal string: '{amount}'")
        dec = Decimal(amount)
    else:
        # amount is Decimal
        if not amount.is_finite():
            raise ValueError(f"Rupee amount must be finite (NaN/Infinity not allowed), got: {amount}")
        if amount < 0 or amount.is_signed():
            raise ValueError(f"Rupee amount cannot be negative, got: {amount}")
        dec = amount

    paise_dec = dec * 100
    if paise_dec != paise_dec.to_integral_value():
        raise ValueError(
            f"Rupee amount does not resolve to an integer number of paise: {amount}"
        )
    return int(paise_dec)


def _format_indian_number(n: int) -> str:
    """Format non-negative integer using Indian digit grouping (lakhs/crores)."""
    s = str(n)
    if len(s) <= 3:
        return s

    last_three = s[-3:]
    remaining = s[:-3]
    groups = []
    while len(remaining) > 2:
        groups.append(remaining[-2:])
        remaining = remaining[:-2]
    if remaining:
        groups.append(remaining)

    groups.reverse()
    return ",".join(groups) + "," + last_three


def format_inr(paise: int) -> str:
    """Format non-negative integer paise as an INR string with Indian digit grouping.

    Examples:
        format_inr(0)           -> "₹0.00"
        format_inr(1)           -> "₹0.01"
        format_inr(123456)      -> "₹1,234.56"
        format_inr(123456789)   -> "₹12,34,567.89"

    Args:
        paise: Non-negative integer paise.

    Returns:
        Formatted INR string prefixed with ₹.

    Raises:
        TypeError: If paise is not an integer (or is a bool).
        ValueError: If paise is negative.
    """
    if isinstance(paise, bool) or not isinstance(paise, int):
        raise TypeError(f"Paise must be an integer, got {type(paise).__name__}")
    if paise < 0:
        raise ValueError(f"Paise amount cannot be negative, got: {paise}")

    rupees = paise // 100
    remainder_paise = paise % 100
    return f"₹{_format_indian_number(rupees)}.{remainder_paise:02d}"


def ceil_div(numerator: int, denominator: int) -> int:
    """Perform integer ceiling division for non-negative numerator and strictly positive denominator.

    Examples:
        ceil_div(100, 30) -> 4
        ceil_div(90, 30)  -> 3
        ceil_div(0, 30)   -> 0
        ceil_div(5, 10)   -> 1

    Args:
        numerator: Non-negative integer.
        denominator: Strictly positive integer.

    Returns:
        Ceiling quotient as integer.

    Raises:
        TypeError: If either operand is not an integer (or is a bool).
        ValueError: If numerator is negative or denominator is not strictly positive.
    """
    if isinstance(numerator, bool) or not isinstance(numerator, int):
        raise TypeError(f"Numerator must be an integer, got {type(numerator).__name__}")
    if isinstance(denominator, bool) or not isinstance(denominator, int):
        raise TypeError(f"Denominator must be an integer, got {type(denominator).__name__}")

    if numerator < 0:
        raise ValueError(f"Numerator cannot be negative, got {numerator}")
    if denominator <= 0:
        raise ValueError(f"Denominator must be strictly positive, got {denominator}")

    return (numerator + denominator - 1) // denominator
