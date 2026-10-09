"""Core time-value-of-money functions (module M3). Pure, deterministic, tested.

Units: money in integer paise, rates in integer basis points (800 = 8.00% a year),
durations in whole months. Internally everything is Decimal; results are rounded
only at the edge (half-up, or up for "how much must I save").

Conventions (chosen to match common Indian SIP / EMI calculators):
- Returns and loan interest: monthly rate = annual rate / 12.
- Regular investments (SIPs) are made at the START of each month (annuity due).
- Loan EMIs are paid at the END of each month.
- Inflation compounds yearly: cost × (1 + i) ^ (months / 12).
"""

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal, getcontext
from typing import Optional

getcontext().prec = 34

_ONE = Decimal(1)
_TEN_K = Decimal(10000)
MAX_MONTHS = 1200  # 100 years: hard stop for any iterative calculation
SETTLE_WITH_LAST_EMI_PAISE = 1000  # ₹10 rounding residue is paid with the last EMI


def _check_money(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be int paise")
    if value < 0:
        raise ValueError(f"{name} cannot be negative")


def _check_months(months: int) -> None:
    if isinstance(months, bool) or not isinstance(months, int):
        raise TypeError("months must be an int")
    if months < 0 or months > MAX_MONTHS:
        raise ValueError(f"months must be between 0 and {MAX_MONTHS}")


def to_paise(value) -> int:
    return int(Decimal(value).quantize(_ONE, rounding=ROUND_HALF_UP))


def to_paise_up(value) -> int:
    return int(Decimal(value).quantize(_ONE, rounding=ROUND_CEILING))


def monthly_rate(annual_bps: int) -> Decimal:
    return Decimal(annual_bps) / _TEN_K / 12


def annual_rate(annual_bps: int) -> Decimal:
    return Decimal(annual_bps) / _TEN_K


# ---------------------------------------------------------------- inflation
def inflate(amount_paise: int, inflation_bps: int, months: int) -> int:
    """Future cost of something that costs `amount_paise` today."""
    _check_money("amount_paise", amount_paise)
    _check_months(months)
    if months == 0 or inflation_bps == 0:
        return amount_paise
    factor = (_ONE + annual_rate(inflation_bps)) ** (Decimal(months) / 12)
    return to_paise(Decimal(amount_paise) * factor)


def deflate(amount_paise: int, inflation_bps: int, months: int) -> int:
    """Today's-money value of a future amount."""
    _check_money("amount_paise", amount_paise)
    _check_months(months)
    if months == 0 or inflation_bps == 0:
        return amount_paise
    factor = (_ONE + annual_rate(inflation_bps)) ** (Decimal(months) / 12)
    return to_paise(Decimal(amount_paise) / factor)


# ---------------------------------------------------------------- growth
def _fv_lump(pv: Decimal, r: Decimal, n: int) -> Decimal:
    return pv * (_ONE + r) ** n


def _annuity_due_factor(r: Decimal, n: int) -> Decimal:
    """Value after n months of 1 paisa invested at the start of every month."""
    if n == 0:
        return Decimal(0)
    if r == 0:
        return Decimal(n)
    return (((_ONE + r) ** n - _ONE) / r) * (_ONE + r)


def future_value(current_paise: int, monthly_paise: int, return_bps: int, months: int) -> int:
    """Value after `months` of a lump sum today plus a monthly SIP at the start of each month."""
    _check_money("current_paise", current_paise)
    _check_money("monthly_paise", monthly_paise)
    _check_months(months)
    r = monthly_rate(return_bps)
    total = _fv_lump(Decimal(current_paise), r, months) + Decimal(monthly_paise) * _annuity_due_factor(r, months)
    return to_paise(total)


def required_monthly(target_paise: int, current_paise: int, return_bps: int, months: int) -> int:
    """Monthly SIP (start of month) needed to reach target, given what is already saved. Rounded up."""
    _check_money("target_paise", target_paise)
    _check_money("current_paise", current_paise)
    _check_months(months)
    r = monthly_rate(return_bps)
    gap = Decimal(target_paise) - _fv_lump(Decimal(current_paise), r, months)
    if gap <= 0:
        return 0
    if months == 0:
        raise ValueError("Target date has arrived but the target is not funded")
    return to_paise_up(gap / _annuity_due_factor(r, months))


def months_to_reach(target_paise: int, current_paise: int, monthly_paise: int, return_bps: int,
                    max_months: int = MAX_MONTHS) -> Optional[int]:
    """Whole months until current savings + SIP reach target; None if not within max_months."""
    _check_money("target_paise", target_paise)
    _check_money("current_paise", current_paise)
    _check_money("monthly_paise", monthly_paise)
    r = monthly_rate(return_bps)
    balance = Decimal(current_paise)
    if balance >= target_paise:
        return 0
    if monthly_paise == 0 and (r == 0 or balance == 0):
        return None
    for month in range(1, max_months + 1):
        balance = (balance + monthly_paise) * (_ONE + r)
        if balance >= target_paise:
            return month
    return None


# ---------------------------------------------------------------- loans
def emi(principal_paise: int, rate_bps: int, months: int) -> int:
    """Standard reducing-balance EMI, paid at month end."""
    _check_money("principal_paise", principal_paise)
    _check_months(months)
    if months == 0:
        raise ValueError("months must be positive")
    if principal_paise == 0:
        return 0
    r = monthly_rate(rate_bps)
    if r == 0:
        return to_paise_up(Decimal(principal_paise) / months)
    growth = (_ONE + r) ** months
    return to_paise(Decimal(principal_paise) * r * growth / (growth - _ONE))


@dataclass(frozen=True)
class Amortization:
    months: Optional[int]          # None when the payment never clears the loan
    total_interest_paise: Optional[int]
    total_paid_paise: Optional[int]
    first_month_interest_paise: int


def amortize(principal_paise: int, rate_bps: int, emi_paise: int, *, extra_monthly_paise: int = 0,
             lump_sum_now_paise: int = 0, max_months: int = MAX_MONTHS) -> Amortization:
    """Simulate a loan month by month (interest on reducing balance, payment at month end)."""
    for name, v in (("principal_paise", principal_paise), ("emi_paise", emi_paise),
                    ("extra_monthly_paise", extra_monthly_paise), ("lump_sum_now_paise", lump_sum_now_paise)):
        _check_money(name, v)
    r = monthly_rate(rate_bps)
    balance = Decimal(max(0, principal_paise - lump_sum_now_paise))
    payment = Decimal(emi_paise + extra_monthly_paise)
    first_interest = to_paise(balance * r)
    if balance == 0:
        return Amortization(0, 0, lump_sum_now_paise, 0)
    if payment <= balance * r:
        return Amortization(None, None, None, first_interest)
    interest_total = Decimal(0)
    paid = Decimal(lump_sum_now_paise)
    for month in range(1, max_months + 1):
        interest = to_paise(balance * r)
        interest_total += interest
        due = balance + interest
        pay = min(payment, due)
        balance = due - pay
        if 0 < balance <= SETTLE_WITH_LAST_EMI_PAISE:
            # Rounding leaves a few paise; lenders collect them with the final EMI.
            pay += balance
            balance = Decimal(0)
        paid += pay
        if balance <= 0:
            return Amortization(month, int(interest_total), int(paid), first_interest)
    return Amortization(None, None, None, first_interest)


# ---------------------------------------------------------------- retirement
def corpus_for_expenses(monthly_expense_paise: int, return_bps: int, inflation_bps: int, months: int) -> int:
    """Corpus needed at the start of a period to pay an expense every month (start of month)
    that grows with inflation, while the remaining corpus earns `return_bps`."""
    _check_money("monthly_expense_paise", monthly_expense_paise)
    _check_months(months)
    if months == 0 or monthly_expense_paise == 0:
        return 0
    r = monthly_rate(return_bps)
    g = (_ONE + annual_rate(inflation_bps)) ** (_ONE / 12) - _ONE
    q = (_ONE + g) / (_ONE + r)  # ratio of successive discounted payments
    if q == _ONE:
        total = Decimal(monthly_expense_paise) * months
    else:
        total = Decimal(monthly_expense_paise) * (_ONE - q ** months) / (_ONE - q)
    return to_paise_up(total)
