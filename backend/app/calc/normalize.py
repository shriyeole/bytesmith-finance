"""Frequency normalisation and ratio helpers. All money is integer paise."""

from enum import Enum


class Frequency(str, Enum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    HALF_YEARLY = "half_yearly"
    YEARLY = "yearly"
    ONE_TIME = "one_time"


_MONTHS_PER_PERIOD = {
    Frequency.MONTHLY: 1,
    Frequency.QUARTERLY: 3,
    Frequency.HALF_YEARLY: 6,
    Frequency.YEARLY: 12,
}


def _div_round_half_up(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        raise ValueError("denominator must be positive")
    if numerator < 0:
        return -_div_round_half_up(-numerator, denominator)
    return (2 * numerator + denominator) // (2 * denominator)


def monthly_equivalent_paise(amount_paise: int, frequency: Frequency | str) -> int:
    """Recurring monthly equivalent of an amount. One-time amounts contribute 0 per month."""
    if isinstance(amount_paise, bool) or not isinstance(amount_paise, int):
        raise TypeError("amount_paise must be an int")
    if amount_paise < 0:
        raise ValueError("amount_paise cannot be negative")
    freq = Frequency(frequency)
    if freq is Frequency.ONE_TIME:
        return 0
    return _div_round_half_up(amount_paise, _MONTHS_PER_PERIOD[freq])


def ratio_bps(numerator: int, denominator: int) -> int | None:
    """numerator / denominator in basis points (10000 = 100%), rounded half up; None if denominator <= 0."""
    if denominator <= 0:
        return None
    return _div_round_half_up(numerator * 10000, denominator)
