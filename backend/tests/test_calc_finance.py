"""Golden-number tests for the M3 calculation library.

Expected values were cross-checked against independent float formulas and against
the figures common Indian EMI / SIP calculators publish for the same inputs.
"""

import pytest

from app.calc.finance import (
    amortize, corpus_for_expenses, deflate, emi, future_value, inflate, months_to_reach, required_monthly,
)

LAKH = 100_000 * 100
CRORE = 100 * LAKH


class TestInflation:
    def test_ten_years_at_six_percent(self):
        assert inflate(10 * LAKH, 600, 120) == 179084770  # ₹17,90,847.70

    def test_partial_years_compound_fractionally(self):
        assert inflate(100_00, 1000, 6) == 10488  # ₹100 × 1.1^0.5
        assert deflate(inflate(10 * LAKH, 600, 60), 600, 60) == 10 * LAKH

    def test_zero_cases(self):
        assert inflate(5 * LAKH, 0, 120) == 5 * LAKH
        assert inflate(5 * LAKH, 600, 0) == 5 * LAKH


class TestGrowth:
    def test_sip_matches_calculators(self):
        # ₹10,000/month, 12%, 10 years, invested at the start of each month
        assert future_value(0, 10_000_00, 1200, 120) == 232339076

    def test_lump_plus_sip(self):
        lump_only = future_value(LAKH, 0, 1200, 12)
        assert lump_only == 11268250  # 1L × 1.01^12
        assert future_value(LAKH, 10_000_00, 1200, 12) == lump_only + future_value(0, 10_000_00, 1200, 12)

    def test_zero_return_is_simple_sum(self):
        assert future_value(LAKH, 5_000_00, 0, 24) == LAKH + 24 * 5_000_00

    def test_required_monthly(self):
        assert required_monthly(CRORE, 0, 1200, 180) == 1981863  # ₹19,818.63, rounded up
        assert future_value(0, 1981863, 1200, 180) >= CRORE
        assert future_value(0, 1981862, 1200, 180) <= CRORE  # one paisa less only reaches it after rounding

    def test_required_monthly_zero_rate_and_already_funded(self):
        assert required_monthly(12 * LAKH, 0, 0, 12) == LAKH
        assert required_monthly(12 * LAKH, 2 * LAKH, 0, 10) == LAKH
        assert required_monthly(LAKH, 2 * LAKH, 800, 12) == 0

    def test_required_monthly_at_deadline(self):
        assert required_monthly(LAKH, LAKH, 0, 0) == 0
        with pytest.raises(ValueError):
            required_monthly(LAKH, 0, 800, 0)

    def test_months_to_reach(self):
        assert months_to_reach(CRORE, 0, 1981863, 1200) == 180
        assert months_to_reach(LAKH, LAKH, 0, 800) == 0
        assert months_to_reach(LAKH, 0, 0, 800) is None
        assert months_to_reach(CRORE, 0, 100_00, 0, max_months=120) is None


class TestLoans:
    def test_emi_matches_published_values(self):
        assert emi(10 * LAKH, 900, 240) == 899726        # ₹8,997.26
        assert emi(50 * LAKH, 850, 240) == 4339116       # ₹43,391.16
        assert emi(12 * LAKH, 0, 12) == LAKH

    def test_full_amortization(self):
        a = amortize(10 * LAKH, 900, 899726)
        assert a.months == 240
        assert a.total_interest_paise == 115934212       # ₹11,59,342.12
        assert a.first_month_interest_paise == 750000    # ₹7,500

    def test_prepayment_shortens_loan(self):
        base = amortize(10 * LAKH, 900, 899726)
        extra = amortize(10 * LAKH, 900, 899726, extra_monthly_paise=2_000_00)
        lump = amortize(10 * LAKH, 900, 899726, lump_sum_now_paise=2 * LAKH)
        assert extra.months < base.months and extra.total_interest_paise < base.total_interest_paise
        assert lump.months < base.months and lump.total_interest_paise < base.total_interest_paise

    def test_payment_below_interest_never_ends(self):
        a = amortize(10 * LAKH, 1200, 10_000_00)  # interest alone is ₹10,000/month
        assert a.months is None and a.total_interest_paise is None

    def test_paid_off_by_lump_sum(self):
        assert amortize(LAKH, 1000, 5_000_00, lump_sum_now_paise=2 * LAKH).months == 0


class TestRetirementCorpus:
    def test_growing_withdrawals(self):
        # ₹50,000/month today's money at retirement start, rising 6%/yr, 25 years, corpus earning 7%
        assert corpus_for_expenses(50_000_00, 700, 600, 300) == 1303831430

    def test_return_equals_growth_is_simple_sum(self):
        # 0% return and 0% inflation: corpus = expense × months
        assert corpus_for_expenses(10_000_00, 0, 0, 120) == 120 * 10_000_00


class TestValidation:
    @pytest.mark.parametrize("bad", [-1, 1.5, True])
    def test_rejects_bad_money(self, bad):
        with pytest.raises((TypeError, ValueError)):
            future_value(bad, 0, 800, 12)

    def test_rejects_bad_months(self):
        with pytest.raises(ValueError):
            inflate(LAKH, 600, 1201)
        with pytest.raises(ValueError):
            inflate(LAKH, 600, -1)
