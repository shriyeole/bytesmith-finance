"""Shared, pure calculation library (module M3). No database or HTTP imports allowed here."""

from app.calc.finance import (
    Amortization, amortize, corpus_for_expenses, deflate, emi, future_value, inflate,
    months_to_reach, required_monthly,
)
from app.calc.normalize import Frequency, monthly_equivalent_paise, ratio_bps
from app.domain.money import ceil_div, format_inr, rupees_to_paise

__all__ = [
    "Amortization", "amortize", "corpus_for_expenses", "deflate", "emi", "future_value", "inflate",
    "months_to_reach", "required_monthly", "Frequency", "monthly_equivalent_paise", "ratio_bps",
    "ceil_div", "format_inr", "rupees_to_paise",
]
