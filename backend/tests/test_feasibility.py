"""Comprehensive unit tests for the pure goal feasibility domain engine.

Tests verify:
- Calendar-month timeline calculations, boundary conditions, and error states.
- Emergency-reserve protection and auto-capping without silent coercion of missing values.
- Integer-paise ceiling division for required monthly savings.
- Four feasibility statuses (FEASIBLE, STRETCH_FEASIBLE, INFEASIBLE, INSUFFICIENT_DATA).
- Zero and negative surplus edge cases and invariant protections.
- Discretionary cut boundary conditions (including exact 100% cut).
- Distinct handling of the three expense categories (fixed commitments, living, discretionary).
- months_needed_at_current_surplus behavior for positive, zero, and negative surplus.
- Complete independence from SQLAlchemy ORM models.
"""

from datetime import date
import pytest

from app.domain.feasibility import (
    FeasibilityResult,
    FeasibilityStatus,
    InvalidTimelineError,
    ProfileBaseline,
    TimelineBasis,
    calculate_calendar_months_remaining,
    calculate_permitted_allocation,
    evaluate_feasibility,
    get_missing_profile_inputs,
    to_profile_baseline,
)


@pytest.fixture
def complete_profile() -> ProfileBaseline:
    """Fixture providing a complete financial profile with ₹60k/month baseline surplus."""
    return ProfileBaseline(
        monthly_take_home_income_paise=15000000,  # ₹1,50,000
        existing_savings_paise=60000000,          # ₹6,00,000
        emergency_reserve_paise=30000000,         # ₹3,00,000 (Unencumbered: ₹3,00,000)
        monthly_fixed_commitments_paise=4500000,  # ₹45,000
        monthly_estimated_living_expenses_paise=2500000,  # ₹25,000
        monthly_estimated_discretionary_paise=2000000,    # ₹20,000
    )


class TestCalendarTimelineCalculation:
    """Verify calendar-month difference and timeline semantics."""

    def test_future_months_same_year(self):
        curr = date(2026, 1, 15)
        tgt = date(2026, 10, 31)
        assert calculate_calendar_months_remaining(curr, tgt) == 9

    def test_future_months_across_year_boundary(self):
        curr = date(2026, 11, 20)
        tgt = date(2027, 2, 10)
        assert calculate_calendar_months_remaining(curr, tgt) == 3

    def test_future_months_multi_year(self):
        curr = date(2026, 10, 2)
        tgt = date(2028, 10, 31)
        assert calculate_calendar_months_remaining(curr, tgt) == 24

    def test_current_calendar_month_is_zero(self):
        curr = date(2026, 10, 2)
        tgt = date(2026, 10, 25)
        assert calculate_calendar_months_remaining(curr, tgt) == 0

    def test_past_calendar_month_is_negative(self):
        curr = date(2026, 10, 2)
        tgt = date(2026, 9, 30)
        assert calculate_calendar_months_remaining(curr, tgt) == -1

        tgt_last_year = date(2025, 10, 2)
        assert calculate_calendar_months_remaining(curr, tgt_last_year) == -12


class TestEmergencyReserveAllocationCap:
    """Verify emergency-reserve protection and upfront allocation capping."""

    def test_exact_allocation_boundary(self):
        # Savings ₹10L, Reserve ₹4L -> Unencumbered ₹6L. Requested ₹6L.
        permitted, is_capped, note = calculate_permitted_allocation(
            requested_paise=60000000,
            existing_savings_paise=100000000,
            emergency_reserve_paise=40000000,
        )
        assert permitted == 60000000
        assert is_capped is False
        assert note is None

    def test_excess_allocation_is_capped_with_note(self):
        # Savings ₹10L, Reserve ₹4L -> Unencumbered ₹6L. Requested ₹8L.
        permitted, is_capped, note = calculate_permitted_allocation(
            requested_paise=80000000,
            existing_savings_paise=100000000,
            emergency_reserve_paise=40000000,
        )
        assert permitted == 60000000
        assert is_capped is True
        assert note is not None
        assert "exceeded unencumbered savings" in note
        assert "Automatically capped" in note

    def test_zero_reserve_boundary(self):
        # Savings ₹5L, Reserve ₹5L -> Unencumbered 0. Requested ₹1L.
        permitted, is_capped, note = calculate_permitted_allocation(
            requested_paise=10000000,
            existing_savings_paise=50000000,
            emergency_reserve_paise=50000000,
        )
        assert permitted == 0
        assert is_capped is True
        assert note is not None

    def test_deficit_reserve_boundary(self):
        # Savings ₹3L, Reserve ₹5L -> Unencumbered 0. Requested ₹50k.
        permitted, is_capped, note = calculate_permitted_allocation(
            requested_paise=5000000,
            existing_savings_paise=30000000,
            emergency_reserve_paise=50000000,
        )
        assert permitted == 0
        assert is_capped is True

    def test_zero_requested_allocation_with_valid_savings(self):
        # Savings ₹10L, Reserve ₹2L. Requested 0 -> Permitted 0, not capped.
        permitted, is_capped, note = calculate_permitted_allocation(
            requested_paise=0,
            existing_savings_paise=100000000,
            emergency_reserve_paise=20000000,
        )
        assert permitted == 0
        assert is_capped is False
        assert note is None

    def test_zero_requested_allocation_with_missing_savings(self):
        # Requested 0 with None savings -> permitted 0 without error, not capped.
        permitted, is_capped, note = calculate_permitted_allocation(
            requested_paise=0,
            existing_savings_paise=None,
            emergency_reserve_paise=None,
        )
        assert permitted == 0
        assert is_capped is False
        assert note is None

    def test_missing_savings_with_positive_request_does_not_convert_to_zero(self):
        # When requested > 0 and savings/reserve are missing, do NOT convert to zero!
        # Return permitted=None to indicate unverified allocation.
        permitted, is_capped, note = calculate_permitted_allocation(
            requested_paise=10000000,
            existing_savings_paise=None,
            emergency_reserve_paise=20000000,
        )
        assert permitted is None
        assert is_capped is False
        assert note is not None
        assert "existing_savings_paise" in note

        permitted2, is_capped2, note2 = calculate_permitted_allocation(
            requested_paise=10000000,
            existing_savings_paise=50000000,
            emergency_reserve_paise=None,
        )
        assert permitted2 is None
        assert "emergency_reserve_paise" in note2

    def test_rejects_negative_requested_allocation(self):
        with pytest.raises(ValueError, match="cannot be negative"):
            calculate_permitted_allocation(-100, 1000, 500)

    def test_rejects_negative_savings_or_reserve(self):
        with pytest.raises(ValueError, match="cannot be negative"):
            calculate_permitted_allocation(100, -500, 500)
        with pytest.raises(ValueError, match="cannot be negative"):
            calculate_permitted_allocation(100, 1000, -200)

    def test_rejects_non_integer_requested_allocation(self):
        with pytest.raises(TypeError):
            calculate_permitted_allocation("1000", 1000, 500)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            calculate_permitted_allocation(True, 1000, 500)    # type: ignore[arg-type]


class TestRequiredMonthlySavingsCalculation:
    """Verify required monthly savings using integer paise and ceiling division."""

    def test_exact_ceiling_division(self, complete_profile: ProfileBaseline):
        # Target ₹1,20,000 over 12 months with 0 allocation -> R = ₹10,000/mo exactly
        result = evaluate_feasibility(
            target_amount_paise=12000000,
            target_date=date(2027, 10, 1),
            requested_allocated_savings_paise=0,
            profile=complete_profile,
            current_date=date(2026, 10, 1),
        )
        assert result.months_remaining == 12
        assert result.net_funding_gap_paise == 12000000
        assert result.required_monthly_savings_paise == 1000000  # ₹10,000

    def test_ceiling_division_rounds_up_remainder(self, complete_profile: ProfileBaseline):
        # Case A: Gap ₹1,20,001.00 (12000100 paise) over 12 months:
        # 12000100 // 12 = 1000008 with remainder 4 -> ceil_div yields 1000009 paise (₹10,000.09)
        result = evaluate_feasibility(
            target_amount_paise=12000100,
            target_date=date(2027, 10, 1),
            requested_allocated_savings_paise=0,
            profile=complete_profile,
            current_date=date(2026, 10, 1),
        )
        assert result.months_remaining == 12
        assert result.net_funding_gap_paise == 12000100
        assert result.required_monthly_savings_paise == 1000009  # Prevents underfunding

        # Case B: Gap of 120001 paise over 12 months:
        # 120001 // 12 = 10000 with remainder 1 -> ceil_div yields 10001 paise
        result_b = evaluate_feasibility(
            target_amount_paise=120001,
            target_date=date(2027, 10, 1),
            requested_allocated_savings_paise=0,
            profile=complete_profile,
            current_date=date(2026, 10, 1),
        )
        assert result_b.required_monthly_savings_paise == 10001

    def test_single_month_horizon(self, complete_profile: ProfileBaseline):
        # Target ₹50,000 over 1 month -> R = ₹50,000/mo
        result = evaluate_feasibility(
            target_amount_paise=5000000,
            target_date=date(2026, 11, 1),
            requested_allocated_savings_paise=0,
            profile=complete_profile,
            current_date=date(2026, 10, 1),
        )
        assert result.months_remaining == 1
        assert result.net_funding_gap_paise == 5000000
        assert result.required_monthly_savings_paise == 5000000


class TestFeasibilityClassification:
    """Verify FEASIBLE, STRETCH_FEASIBLE, and INFEASIBLE classifications."""

    def test_surplus_exceeds_required_is_feasible(self):
        # S = ₹50,000, R = ₹30,000 -> FEASIBLE, buffer = ₹20,000
        profile = ProfileBaseline(
            monthly_take_home_income_paise=10000000,  # ₹1,00,000
            existing_savings_paise=0,
            emergency_reserve_paise=0,
            monthly_fixed_commitments_paise=3000000,  # ₹30,000
            monthly_estimated_living_expenses_paise=1500000,  # ₹15,000
            monthly_estimated_discretionary_paise=500000,     # ₹5,000
            # Outflows: ₹50,000 -> Surplus S = ₹50,000 (5000000 paise)
        )
        # Goal: ₹3,60,000 over 12 months -> R = ₹30,000 (3000000 paise)
        result = evaluate_feasibility(
            target_amount_paise=36000000,
            target_date=date(2027, 10, 1),
            requested_allocated_savings_paise=0,
            profile=profile,
            current_date=date(2026, 10, 1),
        )
        assert result.feasibility_status == FeasibilityStatus.FEASIBLE
        assert result.required_monthly_savings_paise == 3000000
        assert result.baseline_monthly_surplus_paise == 5000000
        assert result.monthly_shortfall_paise == 0
        assert result.required_discretionary_cut_paise == 0
        assert result.monthly_buffer_paise == 2000000
        assert result.months_needed_at_current_surplus == 8  # 36000000 // 5000000 + 1 = 8

    def test_surplus_equals_required_is_feasible(self):
        # S = ₹30,000, R = ₹30,000 -> FEASIBLE, buffer = 0
        profile = ProfileBaseline(
            monthly_take_home_income_paise=8000000,
            existing_savings_paise=0,
            emergency_reserve_paise=0,
            monthly_fixed_commitments_paise=3000000,
            monthly_estimated_living_expenses_paise=1500000,
            monthly_estimated_discretionary_paise=500000,
            # Surplus S = 80k - 50k = 30k
        )
        result = evaluate_feasibility(
            target_amount_paise=36000000,
            target_date=date(2027, 10, 1),
            requested_allocated_savings_paise=0,
            profile=profile,
            current_date=date(2026, 10, 1),
        )
        assert result.feasibility_status == FeasibilityStatus.FEASIBLE
        assert result.monthly_buffer_paise == 0
        assert result.monthly_shortfall_paise == 0

    def test_surplus_deficit_covered_by_discretionary_is_stretch_feasible(self):
        # S = ₹20,000, R = ₹35,000, D = ₹20,000 -> STRETCH_FEASIBLE, required cut = ₹15,000
        profile = ProfileBaseline(
            monthly_take_home_income_paise=10000000,  # ₹1,00,000
            existing_savings_paise=0,
            emergency_reserve_paise=0,
            monthly_fixed_commitments_paise=5000000,  # ₹50,000
            monthly_estimated_living_expenses_paise=1000000,  # ₹10,000
            monthly_estimated_discretionary_paise=2000000,    # ₹20,000 (D)
            # Outflows: ₹80,000 -> Surplus S = ₹20,000
        )
        # Goal: ₹4,20,000 over 12 months -> R = ₹35,000
        result = evaluate_feasibility(
            target_amount_paise=42000000,
            target_date=date(2027, 10, 1),
            requested_allocated_savings_paise=0,
            profile=profile,
            current_date=date(2026, 10, 1),
        )
        assert result.feasibility_status == FeasibilityStatus.STRETCH_FEASIBLE
        assert result.required_monthly_savings_paise == 3500000
        assert result.baseline_monthly_surplus_paise == 2000000
        assert result.required_discretionary_cut_paise == 1500000  # ₹15,000
        assert result.monthly_shortfall_paise == 0
        assert result.months_needed_at_current_surplus == 21  # 42000000 // 2000000 = 21

    def test_discretionary_cut_exactly_equals_available_discretionary(self):
        # S = ₹20,000, R = ₹40,000, D = ₹20,000 -> STRETCH_FEASIBLE (cut = ₹20,000, exactly 100% of D)
        profile = ProfileBaseline(
            monthly_take_home_income_paise=10000000,
            existing_savings_paise=0,
            emergency_reserve_paise=0,
            monthly_fixed_commitments_paise=5000000,
            monthly_estimated_living_expenses_paise=1000000,
            monthly_estimated_discretionary_paise=2000000,
        )
        # Goal: ₹4,80,000 over 12 months -> R = ₹40,000
        result = evaluate_feasibility(
            target_amount_paise=48000000,
            target_date=date(2027, 10, 1),
            requested_allocated_savings_paise=0,
            profile=profile,
            current_date=date(2026, 10, 1),
        )
        assert result.feasibility_status == FeasibilityStatus.STRETCH_FEASIBLE
        assert result.required_discretionary_cut_paise == 2000000  # Exactly equals D
        assert result.monthly_shortfall_paise == 0
        assert result.months_needed_at_current_surplus == 24

    def test_surplus_deficit_exceeds_discretionary_is_infeasible(self):
        # S = ₹20,000, R = ₹50,000, D = ₹20,000 -> INFEASIBLE, shortfall = ₹10,000
        profile = ProfileBaseline(
            monthly_take_home_income_paise=10000000,
            existing_savings_paise=0,
            emergency_reserve_paise=0,
            monthly_fixed_commitments_paise=5000000,
            monthly_estimated_living_expenses_paise=1000000,
            monthly_estimated_discretionary_paise=2000000,
        )
        # Goal: ₹6,00,000 over 12 months -> R = ₹50,000
        result = evaluate_feasibility(
            target_amount_paise=60000000,
            target_date=date(2027, 10, 1),
            requested_allocated_savings_paise=0,
            profile=profile,
            current_date=date(2026, 10, 1),
        )
        assert result.feasibility_status == FeasibilityStatus.INFEASIBLE
        assert result.required_monthly_savings_paise == 5000000
        assert result.monthly_shortfall_paise == 1000000  # 50k - (20k + 20k) = 10k
        assert result.required_discretionary_cut_paise is None
        assert result.months_needed_at_current_surplus == 30  # 60000000 // 2000000 = 30


class TestZeroAndNegativeSurplus:
    """Verify edge cases for zero gap, zero surplus, and negative surplus."""

    def test_zero_funding_gap_is_feasible_even_with_negative_surplus(self):
        # Target ₹5L, Permitted Allocation ₹5L (G = 0), Baseline S = -₹5,000
        profile = ProfileBaseline(
            monthly_take_home_income_paise=5000000,   # ₹50,000
            existing_savings_paise=70000000,          # ₹7,00,000
            emergency_reserve_paise=20000000,         # ₹2,00,000 -> Unencumbered ₹5,00,000
            monthly_fixed_commitments_paise=3000000,  # ₹30,000
            monthly_estimated_living_expenses_paise=2000000,  # ₹20,000
            monthly_estimated_discretionary_paise=500000,     # ₹5,00,000
            # Total Outflows: ₹55,000 -> Surplus S = -₹5,000
        )
        result = evaluate_feasibility(
            target_amount_paise=50000000,  # ₹5,00,000
            target_date=date(2027, 10, 1),
            requested_allocated_savings_paise=50000000,  # ₹5,00,000
            profile=profile,
            current_date=date(2026, 10, 1),
        )
        assert result.net_funding_gap_paise == 0
        assert result.required_monthly_savings_paise == 0
        assert result.feasibility_status == FeasibilityStatus.FEASIBLE
        assert result.baseline_monthly_surplus_paise == -500000
        assert result.monthly_shortfall_paise == 0
        assert result.required_discretionary_cut_paise == 0
        assert result.months_needed_at_current_surplus == 0

    def test_positive_gap_with_zero_surplus_infeasible_when_discretionary_zero(self):
        # Baseline S = 0, R = ₹10,000, D = 0 -> INFEASIBLE, shortfall = ₹10,000
        profile = ProfileBaseline(
            monthly_take_home_income_paise=5000000,   # ₹50,000
            existing_savings_paise=0,
            emergency_reserve_paise=0,
            monthly_fixed_commitments_paise=3000000,  # ₹30,000
            monthly_estimated_living_expenses_paise=2000000,  # ₹20,000
            monthly_estimated_discretionary_paise=0,  # ₹0 (D = 0)
            # Outflows: ₹50,000 -> Surplus S = 0
        )
        result = evaluate_feasibility(
            target_amount_paise=12000000,  # ₹1,20,000 over 12 mos -> R = ₹10,000
            target_date=date(2027, 10, 1),
            requested_allocated_savings_paise=0,
            profile=profile,
            current_date=date(2026, 10, 1),
        )
        assert result.feasibility_status == FeasibilityStatus.INFEASIBLE
        assert result.baseline_monthly_surplus_paise == 0
        assert result.monthly_shortfall_paise == 1000000  # ₹10,000
        assert result.months_needed_at_current_surplus is None  # Non-positive surplus returns None

    def test_positive_gap_with_zero_surplus_recoverable_via_discretionary_spend(self):
        # Baseline S = 0, R = ₹10,000, D = ₹15,000 -> STRETCH_FEASIBLE, cut = ₹10,000
        profile = ProfileBaseline(
            monthly_take_home_income_paise=5000000,   # ₹50,000
            existing_savings_paise=0,
            emergency_reserve_paise=0,
            monthly_fixed_commitments_paise=2000000,  # ₹20,000
            monthly_estimated_living_expenses_paise=1500000,  # ₹15,000
            monthly_estimated_discretionary_paise=1500000,    # ₹15,000 (D)
            # Outflows: ₹50,000 -> Surplus S = 0
        )
        result = evaluate_feasibility(
            target_amount_paise=12000000,
            target_date=date(2027, 10, 1),
            requested_allocated_savings_paise=0,
            profile=profile,
            current_date=date(2026, 10, 1),
        )
        assert result.feasibility_status == FeasibilityStatus.STRETCH_FEASIBLE
        assert result.baseline_monthly_surplus_paise == 0
        assert result.required_discretionary_cut_paise == 1000000  # ₹10,000
        assert result.monthly_shortfall_paise == 0
        assert result.months_needed_at_current_surplus is None  # Surplus is 0 -> None

    def test_positive_gap_with_negative_surplus_recoverable_is_stretch_feasible(self):
        # Baseline S = -₹2,000, R = ₹8,000, D = ₹15,000 -> STRETCH_FEASIBLE (S + D = ₹13,000 >= R)
        profile = ProfileBaseline(
            monthly_take_home_income_paise=5000000,   # ₹50,000
            existing_savings_paise=0,
            emergency_reserve_paise=0,
            monthly_fixed_commitments_paise=2200000,  # ₹22,000
            monthly_estimated_living_expenses_paise=1500000,  # ₹15,000
            monthly_estimated_discretionary_paise=1500000,    # ₹15,000 (D)
            # Outflows: ₹52,000 -> Surplus S = -₹2,000 (-200000 paise)
        )
        # Goal: ₹96,000 over 12 months -> R = ₹8,000
        result = evaluate_feasibility(
            target_amount_paise=9600000,
            target_date=date(2027, 10, 1),
            requested_allocated_savings_paise=0,
            profile=profile,
            current_date=date(2026, 10, 1),
        )
        assert result.feasibility_status == FeasibilityStatus.STRETCH_FEASIBLE
        assert result.baseline_monthly_surplus_paise == -200000
        # Required cut = R - S = 8000 - (-2000) = 10000 (1000000 paise)
        assert result.required_discretionary_cut_paise == 1000000
        assert result.monthly_shortfall_paise == 0
        assert result.months_needed_at_current_surplus is None  # Negative surplus returns None

    def test_positive_gap_with_negative_surplus_unrecoverable_is_infeasible(self):
        # Baseline S = -₹2,000, R = ₹8,000, D = ₹5,000 -> INFEASIBLE (S + D = ₹3,000 < R)
        profile = ProfileBaseline(
            monthly_take_home_income_paise=5000000,   # ₹50,000
            existing_savings_paise=0,
            emergency_reserve_paise=0,
            monthly_fixed_commitments_paise=3200000,  # ₹32,000
            monthly_estimated_living_expenses_paise=1500000,  # ₹15,000
            monthly_estimated_discretionary_paise=500000,     # ₹5,000 (D)
            # Outflows: ₹52,000 -> Surplus S = -₹2,000 (-200000 paise)
        )
        # Goal: ₹96,000 over 12 months -> R = ₹8,000
        result = evaluate_feasibility(
            target_amount_paise=9600000,
            target_date=date(2027, 10, 1),
            requested_allocated_savings_paise=0,
            profile=profile,
            current_date=date(2026, 10, 1),
        )
        assert result.feasibility_status == FeasibilityStatus.INFEASIBLE
        assert result.baseline_monthly_surplus_paise == -200000
        # Shortfall = R - (S + D) = 8000 - (-2000 + 5000) = 8000 - 3000 = 5000 (500000 paise)
        assert result.monthly_shortfall_paise == 500000
        assert result.required_discretionary_cut_paise is None
        assert result.months_needed_at_current_surplus is None

    def test_negative_or_zero_surplus_cannot_be_reported_as_feasible_when_gap_positive(self):
        # Invariant check: When gap > 0 and surplus <= 0, status must NEVER be FEASIBLE
        profile_neg = ProfileBaseline(
            monthly_take_home_income_paise=4000000,
            existing_savings_paise=0,
            emergency_reserve_paise=0,
            monthly_fixed_commitments_paise=3000000,
            monthly_estimated_living_expenses_paise=2000000,
            monthly_estimated_discretionary_paise=1000000,
            # Surplus S = 40k - 60k = -20k
        )
        result_neg = evaluate_feasibility(
            target_amount_paise=1000000,  # ₹10,000 gap
            target_date=date(2027, 10, 1),
            requested_allocated_savings_paise=0,
            profile=profile_neg,
            current_date=date(2026, 10, 1),
        )
        assert result_neg.feasibility_status != FeasibilityStatus.FEASIBLE

        profile_zero = ProfileBaseline(
            monthly_take_home_income_paise=6000000,
            existing_savings_paise=0,
            emergency_reserve_paise=0,
            monthly_fixed_commitments_paise=3000000,
            monthly_estimated_living_expenses_paise=2000000,
            monthly_estimated_discretionary_paise=1000000,
            # Surplus S = 60k - 60k = 0
        )
        result_zero = evaluate_feasibility(
            target_amount_paise=1000000,  # ₹10,000 gap
            target_date=date(2027, 10, 1),
            requested_allocated_savings_paise=0,
            profile=profile_zero,
            current_date=date(2026, 10, 1),
        )
        assert result_zero.feasibility_status != FeasibilityStatus.FEASIBLE


class TestTimelineBoundaries:
    """Verify deadline validation, current-month limits, and past date rejection."""

    def test_past_target_date_rejected_on_complete_profile(self, complete_profile: ProfileBaseline):
        with pytest.raises(InvalidTimelineError) as exc_info:
            evaluate_feasibility(
                target_amount_paise=10000000,
                target_date=date(2026, 8, 15),
                requested_allocated_savings_paise=0,
                profile=complete_profile,
                current_date=date(2026, 10, 1),
            )
        assert exc_info.value.error_code == "INVALID_TIMELINE"
        assert exc_info.value.months_remaining < 0

    def test_past_target_date_rejected_on_incomplete_profile(self):
        # Even with incomplete profile, past target date must raise InvalidTimelineError
        incomplete = ProfileBaseline(
            monthly_take_home_income_paise=None,
            existing_savings_paise=None,
        )
        with pytest.raises(InvalidTimelineError) as exc_info:
            evaluate_feasibility(
                target_amount_paise=10000000,
                target_date=date(2026, 8, 15),
                requested_allocated_savings_paise=0,
                profile=incomplete,
                current_date=date(2026, 10, 1),
            )
        assert exc_info.value.error_code == "INVALID_TIMELINE"
        assert exc_info.value.months_remaining < 0

    def test_current_month_deadline_with_unfunded_gap_rejected_on_complete_profile(
        self, complete_profile: ProfileBaseline
    ):
        with pytest.raises(InvalidTimelineError) as exc_info:
            evaluate_feasibility(
                target_amount_paise=10000000,
                target_date=date(2026, 10, 25),  # Same month (M = 0)
                requested_allocated_savings_paise=0,
                profile=complete_profile,
                current_date=date(2026, 10, 2),
            )
        assert exc_info.value.error_code == "INVALID_TIMELINE"
        assert exc_info.value.months_remaining == 0
        assert "0 future saving cycles remain" in str(exc_info.value)

    def test_current_month_deadline_with_unfunded_gap_rejected_on_incomplete_profile(self):
        # Target in current month with unfunded gap on incomplete profile raises InvalidTimelineError
        incomplete = ProfileBaseline(
            monthly_take_home_income_paise=15000000,
            existing_savings_paise=None,  # Missing
            emergency_reserve_paise=None, # Missing
        )
        with pytest.raises(InvalidTimelineError) as exc_info:
            evaluate_feasibility(
                target_amount_paise=10000000,
                target_date=date(2026, 10, 25),
                requested_allocated_savings_paise=0,
                profile=incomplete,
                current_date=date(2026, 10, 2),
            )
        assert exc_info.value.error_code == "INVALID_TIMELINE"
        assert exc_info.value.months_remaining == 0

    def test_current_month_deadline_fully_funded_is_feasible(self, complete_profile: ProfileBaseline):
        # Target ₹2L, Allocated ₹2L -> Funding gap = 0 in current month is FEASIBLE
        result = evaluate_feasibility(
            target_amount_paise=20000000,
            target_date=date(2026, 10, 25),
            requested_allocated_savings_paise=20000000,
            profile=complete_profile,
            current_date=date(2026, 10, 2),
        )
        assert result.net_funding_gap_paise == 0
        assert result.months_remaining == 0
        assert result.feasibility_status == FeasibilityStatus.FEASIBLE
        assert result.required_monthly_savings_paise == 0


class TestIncompleteProfileHandling:
    """Verify Option B permissive behavior: INSUFFICIENT_DATA and diagnostic output."""

    def test_missing_living_expenses_returns_insufficient_data(self):
        partial = ProfileBaseline(
            monthly_take_home_income_paise=15000000,
            existing_savings_paise=60000000,
            emergency_reserve_paise=30000000,
            monthly_fixed_commitments_paise=4500000,
            monthly_estimated_living_expenses_paise=None,  # Missing!
            monthly_estimated_discretionary_paise=2000000,
        )
        result = evaluate_feasibility(
            target_amount_paise=150000000,  # ₹15,00,000
            target_date=date(2027, 10, 31),
            requested_allocated_savings_paise=30000000,  # ₹3,00,000 -> Gap = ₹12,00,000
            profile=partial,
            current_date=date(2026, 10, 1),
        )
        assert result.feasibility_status == FeasibilityStatus.INSUFFICIENT_DATA
        assert result.months_remaining == 12
        assert result.net_funding_gap_paise == 120000000
        assert result.required_monthly_savings_paise == 10000000
        # Cash-flow surplus is withheld
        assert result.baseline_monthly_surplus_paise is None
        assert result.monthly_discretionary_spend_paise is None
        assert result.monthly_shortfall_paise is None
        assert result.required_discretionary_cut_paise is None
        assert result.months_needed_at_current_surplus is None
        assert result.missing_baseline_inputs == ["monthly_estimated_living_expenses_paise"]
        assert "Feasibility cannot be determined" in result.actionable_insight

    def test_missing_savings_and_reserve_with_requested_allocation(self):
        # When savings and reserve are missing and requested_allocation > 0:
        # Do not convert to 0! Permitted allocation and gap must remain None.
        partial = ProfileBaseline(
            monthly_take_home_income_paise=15000000,
            existing_savings_paise=None,   # Missing
            emergency_reserve_paise=None,  # Missing
            monthly_fixed_commitments_paise=4500000,
            monthly_estimated_living_expenses_paise=2500000,
            monthly_estimated_discretionary_paise=2000000,
        )
        result = evaluate_feasibility(
            target_amount_paise=100000000,
            target_date=date(2027, 10, 1),
            requested_allocated_savings_paise=30000000,  # User requested ₹3L allocation
            profile=partial,
            current_date=date(2026, 10, 1),
        )
        assert result.feasibility_status == FeasibilityStatus.INSUFFICIENT_DATA
        assert result.permitted_allocated_savings_paise is None  # Not assumed 0!
        assert result.net_funding_gap_paise is None              # Not falsely computed!
        assert result.required_monthly_savings_paise is None     # Not falsely computed!
        assert "existing_savings_paise" in result.missing_baseline_inputs
        assert "emergency_reserve_paise" in result.missing_baseline_inputs
        assert "cannot be verified" in result.actionable_insight

    def test_missing_savings_with_zero_requested_allocation_computes_exact_gap(self):
        # When requested_allocation == 0, savings/reserve being missing does NOT block gap calculation!
        partial = ProfileBaseline(
            monthly_take_home_income_paise=15000000,
            existing_savings_paise=None,
            emergency_reserve_paise=None,
            monthly_fixed_commitments_paise=4500000,
            monthly_estimated_living_expenses_paise=None,  # Living expenses missing
            monthly_estimated_discretionary_paise=2000000,
        )
        result = evaluate_feasibility(
            target_amount_paise=120000000,  # ₹12L
            target_date=date(2027, 10, 1),
            requested_allocated_savings_paise=0,  # No savings requested
            profile=partial,
            current_date=date(2026, 10, 1),
        )
        assert result.feasibility_status == FeasibilityStatus.INSUFFICIENT_DATA
        assert result.permitted_allocated_savings_paise == 0
        assert result.net_funding_gap_paise == 120000000
        assert result.required_monthly_savings_paise == 10000000
        assert "monthly_estimated_living_expenses_paise" in result.missing_baseline_inputs

    def test_incomplete_profile_zero_gap_returns_insufficient_data(self):
        # Even if G = 0, an incomplete profile does not present a definitive financial picture
        partial = ProfileBaseline(
            monthly_take_home_income_paise=15000000,
            existing_savings_paise=60000000,
            emergency_reserve_paise=30000000,
            monthly_fixed_commitments_paise=4500000,
            monthly_estimated_living_expenses_paise=None,
            monthly_estimated_discretionary_paise=None,
        )
        result = evaluate_feasibility(
            target_amount_paise=30000000,
            target_date=date(2027, 10, 1),
            requested_allocated_savings_paise=30000000,  # Covers target upfront
            profile=partial,
            current_date=date(2026, 10, 1),
        )
        assert result.net_funding_gap_paise == 0
        assert result.required_monthly_savings_paise == 0
        assert result.feasibility_status == FeasibilityStatus.INSUFFICIENT_DATA
        assert len(result.missing_baseline_inputs) == 2


class TestDistinctExpenseCategories:
    """Verify that fixed commitments, living expenses, and discretionary spending are distinct."""

    def test_expense_categories_distinctness_in_flexibility(self):
        # Two profiles with identical income (₹1,00,000) and identical total expenses (₹80,000)
        # -> Identical baseline surplus S = ₹20,000.
        # But Profile A has high fixed/living and low discretionary (D = ₹10,000).
        # Profile B has low fixed/living and high discretionary (D = ₹50,000).
        profile_rigid = ProfileBaseline(
            monthly_take_home_income_paise=10000000,  # ₹1,00,000
            existing_savings_paise=0,
            emergency_reserve_paise=0,
            monthly_fixed_commitments_paise=5000000,  # ₹50,000 (rigid)
            monthly_estimated_living_expenses_paise=2000000,  # ₹20,000 (rigid)
            monthly_estimated_discretionary_paise=1000000,    # ₹10,000 (flexible, D)
            # Outflows = ₹80,000, Surplus S = ₹20,000
        )
        profile_flexible = ProfileBaseline(
            monthly_take_home_income_paise=10000000,  # ₹1,00,000
            existing_savings_paise=0,
            emergency_reserve_paise=0,
            monthly_fixed_commitments_paise=1000000,  # ₹10,000
            monthly_estimated_living_expenses_paise=2000000,  # ₹20,000
            monthly_estimated_discretionary_paise=5000000,    # ₹50,000 (flexible, D)
            # Outflows = ₹80,000, Surplus S = ₹20,000
        )

        # Both evaluated for goal requiring R = ₹40,000/month:
        # Profile A: S + D = 20k + 10k = 30k < 40k -> INFEASIBLE (fixed/living cannot be cut!)
        result_rigid = evaluate_feasibility(
            target_amount_paise=48000000,  # R = ₹40,000 over 12 mos
            target_date=date(2027, 10, 1),
            requested_allocated_savings_paise=0,
            profile=profile_rigid,
            current_date=date(2026, 10, 1),
        )
        assert result_rigid.feasibility_status == FeasibilityStatus.INFEASIBLE
        assert result_rigid.monthly_shortfall_paise == 1000000  # ₹10,000 shortfall

        # Profile B: S + D = 20k + 50k = 70k >= 40k -> STRETCH_FEASIBLE!
        result_flexible = evaluate_feasibility(
            target_amount_paise=48000000,
            target_date=date(2027, 10, 1),
            requested_allocated_savings_paise=0,
            profile=profile_flexible,
            current_date=date(2026, 10, 1),
        )
        assert result_flexible.feasibility_status == FeasibilityStatus.STRETCH_FEASIBLE
        assert result_flexible.required_discretionary_cut_paise == 2000000  # Cut ₹20,000 of D


class TestExplicitZeroExpensesIntegrity:
    """Verify that explicitly entered 0 paise is distinguished from None and evaluated definitively."""

    def test_explicit_zero_expenses_complete_and_feasible(self):
        # Living = 0, Discretionary = 0, Income = ₹1,00,000, Fixed = ₹30,000 -> Surplus = ₹70,000
        profile = ProfileBaseline(
            monthly_take_home_income_paise=10000000,
            existing_savings_paise=0,
            emergency_reserve_paise=0,
            monthly_fixed_commitments_paise=3000000,
            monthly_estimated_living_expenses_paise=0,  # Explicit zero
            monthly_estimated_discretionary_paise=0,    # Explicit zero
        )
        assert profile.is_complete is True

        result = evaluate_feasibility(
            target_amount_paise=60000000,  # R = ₹50,000/mo over 12 mos
            target_date=date(2027, 10, 1),
            requested_allocated_savings_paise=0,
            profile=profile,
            current_date=date(2026, 10, 1),
        )
        assert result.feasibility_status == FeasibilityStatus.FEASIBLE
        assert result.baseline_monthly_surplus_paise == 7000000
        assert result.monthly_discretionary_spend_paise == 0
        assert result.monthly_shortfall_paise == 0

    def test_explicit_zero_expenses_infeasible_when_deficit(self):
        # Living = 0, Disc = 0, Fixed = ₹60,000, Income = ₹50,000 -> Surplus = -₹10,000
        profile = ProfileBaseline(
            monthly_take_home_income_paise=5000000,
            existing_savings_paise=0,
            emergency_reserve_paise=0,
            monthly_fixed_commitments_paise=6000000,
            monthly_estimated_living_expenses_paise=0,
            monthly_estimated_discretionary_paise=0,
        )
        result = evaluate_feasibility(
            target_amount_paise=12000000,  # R = ₹10,000/mo over 12 mos
            target_date=date(2027, 10, 1),
            requested_allocated_savings_paise=0,
            profile=profile,
            current_date=date(2026, 10, 1),
        )
        assert result.feasibility_status == FeasibilityStatus.INFEASIBLE
        assert result.baseline_monthly_surplus_paise == -1000000
        # Shortfall = R - (S + D) = 10k - (-10k + 0) = 20k (2000000 paise)
        assert result.monthly_shortfall_paise == 2000000


class TestPureDomainDecoupling:
    """Verify that pure domain calculations work with plain dicts and ProfileBaseline."""

    def test_evaluates_with_plain_dictionary(self):
        profile_dict = {
            "monthly_take_home_income_paise": 15000000,
            "existing_savings_paise": 60000000,
            "emergency_reserve_paise": 30000000,
            "monthly_fixed_commitments_paise": 4500000,
            "monthly_estimated_living_expenses_paise": 2500000,
            "monthly_estimated_discretionary_paise": 2000000,
        }
        result = evaluate_feasibility(
            target_amount_paise=120000000,
            target_date=date(2027, 10, 1),
            requested_allocated_savings_paise=30000000,
            profile=profile_dict,
            current_date=date(2026, 10, 1),
        )
        assert result.feasibility_status == FeasibilityStatus.STRETCH_FEASIBLE
        assert result.net_funding_gap_paise == 90000000
        assert result.required_monthly_savings_paise == 7500000
        assert result.required_discretionary_cut_paise == 1500000


class TestInputValidation:
    """Verify rejection of invalid types and invalid numeric inputs."""

    def test_rejects_non_positive_target_amount(self, complete_profile: ProfileBaseline):
        with pytest.raises(ValueError, match="strictly positive"):
            evaluate_feasibility(
                target_amount_paise=0,
                target_date=date(2027, 10, 1),
                requested_allocated_savings_paise=0,
                profile=complete_profile,
            )
        with pytest.raises(ValueError, match="strictly positive"):
            evaluate_feasibility(
                target_amount_paise=-1000,
                target_date=date(2027, 10, 1),
                requested_allocated_savings_paise=0,
                profile=complete_profile,
            )

    def test_rejects_invalid_types_for_amounts(self, complete_profile: ProfileBaseline):
        with pytest.raises(TypeError):
            evaluate_feasibility(
                target_amount_paise="10000",  # type: ignore[arg-type]
                target_date=date(2027, 10, 1),
                requested_allocated_savings_paise=0,
                profile=complete_profile,
            )
        with pytest.raises(TypeError):
            evaluate_feasibility(
                target_amount_paise=True,     # type: ignore[arg-type]
                target_date=date(2027, 10, 1),
                requested_allocated_savings_paise=0,
                profile=complete_profile,
            )
