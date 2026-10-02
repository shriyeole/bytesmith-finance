"""Pure goal feasibility domain engine for ByteSmiths Finance Copilot.

This module provides business calculations for financial goal feasibility:
- Emergency reserve allocation capping
- Calendar-month timeline evaluation
- Net funding gap calculation
- Required monthly savings calculation using ceiling division
- Decision tree for feasibility status (FEASIBLE, STRETCH_FEASIBLE, INFEASIBLE, INSUFFICIENT_DATA)

It is completely decoupled from database models and persistence frameworks.
"""

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any, List, Optional

from app.domain.money import ceil_div, format_inr


class FeasibilityStatus(str, Enum):
    """The four canonical financial feasibility statuses for a goal."""

    FEASIBLE = "FEASIBLE"
    STRETCH_FEASIBLE = "STRETCH_FEASIBLE"
    INFEASIBLE = "INFEASIBLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class InvalidTimelineError(ValueError):
    """Raised when goal target date has an invalid timeline (past or current month with positive gap)."""

    def __init__(
        self,
        message: str,
        error_code: str = "INVALID_TIMELINE",
        months_remaining: int = 0,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.months_remaining = months_remaining


@dataclass(frozen=True)
class TimelineBasis:
    """Human-readable and structured breakdown of the calendar-month timeline."""

    current_month: str
    target_month: str
    saving_cycles_count: int
    explanation: str


@dataclass(frozen=True)
class ProfileBaseline:
    """Pure domain representation of a user's financial profile inputs.

    Decoupled from SQLAlchemy ORM models.
    """

    monthly_take_home_income_paise: Optional[int] = None
    existing_savings_paise: Optional[int] = None
    emergency_reserve_paise: Optional[int] = None
    monthly_fixed_commitments_paise: Optional[int] = None
    monthly_estimated_living_expenses_paise: Optional[int] = None
    monthly_estimated_discretionary_paise: Optional[int] = None

    @property
    def is_complete(self) -> bool:
        """Check whether all baseline monetary fields are present and valid."""
        if (
            self.monthly_take_home_income_paise is None
            or self.monthly_take_home_income_paise <= 0
        ):
            return False
        if self.existing_savings_paise is None or self.existing_savings_paise < 0:
            return False
        if self.emergency_reserve_paise is None or self.emergency_reserve_paise < 0:
            return False
        if (
            self.monthly_fixed_commitments_paise is None
            or self.monthly_fixed_commitments_paise < 0
        ):
            return False
        if (
            self.monthly_estimated_living_expenses_paise is None
            or self.monthly_estimated_living_expenses_paise < 0
        ):
            return False
        if (
            self.monthly_estimated_discretionary_paise is None
            or self.monthly_estimated_discretionary_paise < 0
        ):
            return False
        if self.emergency_reserve_paise > self.existing_savings_paise:
            return False
        return True


def to_profile_baseline(profile: Any) -> ProfileBaseline:
    """Convert an arbitrary profile object, ORM model, or dictionary into a pure ProfileBaseline."""
    if isinstance(profile, ProfileBaseline):
        return profile
    if isinstance(profile, dict):
        return ProfileBaseline(
            monthly_take_home_income_paise=profile.get("monthly_take_home_income_paise"),
            existing_savings_paise=profile.get("existing_savings_paise"),
            emergency_reserve_paise=profile.get("emergency_reserve_paise"),
            monthly_fixed_commitments_paise=profile.get("monthly_fixed_commitments_paise"),
            monthly_estimated_living_expenses_paise=profile.get(
                "monthly_estimated_living_expenses_paise"
            ),
            monthly_estimated_discretionary_paise=profile.get(
                "monthly_estimated_discretionary_paise"
            ),
        )
    return ProfileBaseline(
        monthly_take_home_income_paise=getattr(profile, "monthly_take_home_income_paise", None),
        existing_savings_paise=getattr(profile, "existing_savings_paise", None),
        emergency_reserve_paise=getattr(profile, "emergency_reserve_paise", None),
        monthly_fixed_commitments_paise=getattr(profile, "monthly_fixed_commitments_paise", None),
        monthly_estimated_living_expenses_paise=getattr(
            profile, "monthly_estimated_living_expenses_paise", None
        ),
        monthly_estimated_discretionary_paise=getattr(
            profile, "monthly_estimated_discretionary_paise", None
        ),
    )


@dataclass(frozen=True)
class FeasibilityResult:
    """Deterministic feasibility evaluation result for a financial goal."""

    goal_id: Optional[str]
    title: str
    target_amount_paise: int
    target_date: date
    months_remaining: int
    requested_allocated_savings_paise: int
    permitted_allocated_savings_paise: Optional[int]
    is_allocation_capped: bool
    allocation_capping_note: Optional[str]
    net_funding_gap_paise: Optional[int]
    required_monthly_savings_paise: Optional[int]
    baseline_monthly_surplus_paise: Optional[int]
    monthly_discretionary_spend_paise: Optional[int]
    feasibility_status: FeasibilityStatus
    monthly_shortfall_paise: Optional[int]
    required_discretionary_cut_paise: Optional[int]
    months_needed_at_current_surplus: Optional[int]
    missing_baseline_inputs: List[str]
    actionable_insight: str
    timeline_basis: TimelineBasis

    @property
    def monthly_buffer_paise(self) -> Optional[int]:
        """Surplus buffer remaining after meeting required monthly savings."""
        if (
            self.baseline_monthly_surplus_paise is not None
            and self.required_monthly_savings_paise is not None
        ):
            return max(
                0, self.baseline_monthly_surplus_paise - self.required_monthly_savings_paise
            )
        return None


def calculate_calendar_months_remaining(current_date: date, target_date: date) -> int:
    """Calculate the number of eligible future monthly saving cycles between two dates.

    Formula:
        ΔM = (target_date.year - current_date.year) * 12 + (target_date.month - current_date.month)

    Args:
        current_date: Baseline date (typically current date).
        target_date: Target deadline date.

    Returns:
        Integer number of calendar months (ΔM). Can be negative (past), 0 (current month), or >= 1 (future).
    """
    return (target_date.year - current_date.year) * 12 + (target_date.month - current_date.month)


def build_timeline_basis(
    current_date: date, target_date: date, months_remaining: int
) -> TimelineBasis:
    """Construct structured explanation for the calendar-month saving horizon."""
    curr_str = f"{current_date.year:04d}-{current_date.month:02d}"
    tgt_str = f"{target_date.year:04d}-{target_date.month:02d}"

    if months_remaining > 0:
        explanation = (
            f"{months_remaining} future monthly saving cycle(s) between {curr_str} and {tgt_str}. "
            f"The current month ({curr_str}) is treated as underway and is not counted as a future savings cycle."
        )
    elif months_remaining == 0:
        explanation = (
            f"Target deadline is within the current month ({curr_str}). "
            f"0 future saving cycles remain."
        )
    else:
        explanation = (
            f"Target deadline ({tgt_str}) is in the past compared to current month ({curr_str})."
        )

    return TimelineBasis(
        current_month=curr_str,
        target_month=tgt_str,
        saving_cycles_count=months_remaining,
        explanation=explanation,
    )


def _format_signed_inr(paise: int) -> str:
    """Format potentially negative or non-negative integer paise as an INR string."""
    if paise < 0:
        return f"-{format_inr(-paise)}"
    return format_inr(paise)


def get_missing_profile_inputs(profile: Any) -> List[str]:
    """Identify which required monetary fields in profile are missing or invalid."""
    p = to_profile_baseline(profile)
    missing: List[str] = []
    if (
        p.monthly_take_home_income_paise is None
        or p.monthly_take_home_income_paise <= 0
    ):
        missing.append("monthly_take_home_income_paise")
    if p.existing_savings_paise is None or p.existing_savings_paise < 0:
        missing.append("existing_savings_paise")
    if p.emergency_reserve_paise is None or p.emergency_reserve_paise < 0:
        missing.append("emergency_reserve_paise")
    if (
        p.monthly_fixed_commitments_paise is None
        or p.monthly_fixed_commitments_paise < 0
    ):
        missing.append("monthly_fixed_commitments_paise")
    if (
        p.monthly_estimated_living_expenses_paise is None
        or p.monthly_estimated_living_expenses_paise < 0
    ):
        missing.append("monthly_estimated_living_expenses_paise")
    if (
        p.monthly_estimated_discretionary_paise is None
        or p.monthly_estimated_discretionary_paise < 0
    ):
        missing.append("monthly_estimated_discretionary_paise")
    return missing


def calculate_permitted_allocation(
    requested_paise: int,
    existing_savings_paise: Optional[int],
    emergency_reserve_paise: Optional[int],
) -> tuple[Optional[int], bool, Optional[str]]:
    """Enforce emergency reserve protection on requested upfront savings allocation.

    Rules:
        - If requested_paise == 0: allocation is 0, is_capped is False, note is None.
          No savings are drawn, so missing savings/reserve does not block 0 allocation.
        - If requested_paise > 0:
          If existing_savings_paise is None or emergency_reserve_paise is None:
              Do not convert missing values to zero. Return permitted=None, is_capped=False,
              and an explanatory note indicating missing inputs.
          Unencumbered savings U = max(0, existing_savings_paise - emergency_reserve_paise).
          Permitted allocation A = min(requested_paise, U).
          Flag is_capped = (requested_paise > U).
    """
    if isinstance(requested_paise, bool) or not isinstance(requested_paise, int):
        raise TypeError(f"Requested allocation must be an integer, got {type(requested_paise).__name__}")
    if requested_paise < 0:
        raise ValueError(f"Requested allocation cannot be negative, got {requested_paise}")

    if existing_savings_paise is not None and existing_savings_paise < 0:
        raise ValueError(f"Existing savings cannot be negative, got {existing_savings_paise}")
    if emergency_reserve_paise is not None and emergency_reserve_paise < 0:
        raise ValueError(f"Emergency reserve cannot be negative, got {emergency_reserve_paise}")

    if existing_savings_paise is not None and emergency_reserve_paise is not None:
        if emergency_reserve_paise > existing_savings_paise:
            raise ValueError(
                f"Emergency reserve ({format_inr(emergency_reserve_paise)}) cannot exceed "
                f"existing savings ({format_inr(existing_savings_paise)})."
            )

    if requested_paise == 0:
        return 0, False, None

    if existing_savings_paise is None or emergency_reserve_paise is None:
        missing = []
        if existing_savings_paise is None:
            missing.append("existing_savings_paise")
        if emergency_reserve_paise is None:
            missing.append("emergency_reserve_paise")
        note = (
            f"Requested allocation of {format_inr(requested_paise)} cannot be evaluated because "
            f"baseline inputs are missing: {', '.join(missing)}."
        )
        return None, False, note

    unencumbered = max(0, existing_savings_paise - emergency_reserve_paise)
    permitted = min(requested_paise, unencumbered)
    is_capped = requested_paise > unencumbered

    capping_note: Optional[str] = None
    if is_capped:
        capping_note = (
            f"Requested allocation of {format_inr(requested_paise)} exceeded unencumbered savings "
            f"of {format_inr(unencumbered)}. Automatically capped at {format_inr(permitted)} "
            f"to preserve emergency reserve."
        )

    return permitted, is_capped, capping_note


def evaluate_feasibility(
    target_amount_paise: int,
    target_date: date,
    requested_allocated_savings_paise: int = 0,
    profile: Any = None,
    goal_id: Optional[str] = None,
    title: str = "Financial Goal",
    current_date: Optional[date] = None,
) -> FeasibilityResult:
    """Evaluate financial goal feasibility using pure integer paise domain logic.

    Args:
        target_amount_paise: Target goal amount in integer paise (strictly positive).
        target_date: Target deadline date.
        requested_allocated_savings_paise: Upfront savings requested to allocate (non-negative).
        profile: ProfileBaseline, dictionary, or duck-typed profile model.
        goal_id: Optional identifier of the goal.
        title: Title of the goal.
        current_date: Reference current date (defaults to date.today()).

    Returns:
        FeasibilityResult with complete metrics, status, and explanations.

    Raises:
        TypeError: If numeric inputs are invalid types.
        ValueError: If target amount is not positive or requested allocation is negative.
        InvalidTimelineError: If target date is in the past, or in the current month with a funding gap.
    """
    if isinstance(target_amount_paise, bool) or not isinstance(target_amount_paise, int):
        raise TypeError(f"Target amount must be an integer, got {type(target_amount_paise).__name__}")
    if target_amount_paise <= 0:
        raise ValueError(f"Target amount must be strictly positive, got {target_amount_paise}")

    p = to_profile_baseline(profile)

    if current_date is None:
        current_date = date.today()

    # 1. Calendar month timeline
    months_remaining = calculate_calendar_months_remaining(current_date, target_date)
    timeline_basis = build_timeline_basis(current_date, target_date, months_remaining)

    # 2. Timeline validation: Past deadline is rejected regardless of profile completeness
    if months_remaining < 0:
        raise InvalidTimelineError(
            f"Target deadline ({target_date}) is in the past compared to current date ({current_date}).",
            error_code="INVALID_TIMELINE",
            months_remaining=months_remaining,
        )

    # 3. Permitted allocation calculation
    permitted_allocation, is_capped, capping_note = calculate_permitted_allocation(
        requested_paise=requested_allocated_savings_paise,
        existing_savings_paise=p.existing_savings_paise,
        emergency_reserve_paise=p.emergency_reserve_paise,
    )

    # 4. Funding gap calculation
    funding_gap: Optional[int] = None
    if permitted_allocation is not None:
        funding_gap = max(0, target_amount_paise - permitted_allocation)

    # 5. Timeline validation: Current-month deadline with positive or unknown funding gap is rejected
    if months_remaining == 0:
        if funding_gap is None or funding_gap > 0:
            gap_desc = f"an unfunded gap of {format_inr(funding_gap)}" if funding_gap is not None else "an unverified funding gap"
            raise InvalidTimelineError(
                f"Target deadline ({target_date}) is within the current calendar month with {gap_desc}. "
                f"Current month has 0 future saving cycles remaining.",
                error_code="INVALID_TIMELINE",
                months_remaining=months_remaining,
            )

    # 6. Required monthly savings calculation
    required_monthly_savings: Optional[int] = None
    if funding_gap is not None:
        if funding_gap == 0:
            required_monthly_savings = 0
        else:
            # months_remaining >= 1
            required_monthly_savings = ceil_div(funding_gap, months_remaining)

    # 7. Check profile completeness (Option B Permissive Handling)
    if not p.is_complete or funding_gap is None:
        missing_inputs = get_missing_profile_inputs(p)
        if funding_gap is None:
            insight = (
                f"Requested upfront savings allocation of {format_inr(requested_allocated_savings_paise)} "
                f"cannot be verified because baseline inputs are missing: {', '.join(missing_inputs)}. "
                f"Please provide these baseline inputs to calculate permitted allocation and funding gap."
            )
        elif funding_gap == 0:
            insight = (
                "Your goal is fully funded upfront by permitted savings allocation, but profile baseline "
                f"inputs are incomplete: {', '.join(missing_inputs)}."
            )
        else:
            insight = (
                f"You need to save {format_inr(required_monthly_savings)}/month over {months_remaining} months "
                f"to bridge the {format_inr(funding_gap)} gap. Feasibility cannot be determined until you "
                f"provide estimates for: {', '.join(missing_inputs)}."
            )

        return FeasibilityResult(
            goal_id=goal_id,
            title=title,
            target_amount_paise=target_amount_paise,
            target_date=target_date,
            months_remaining=months_remaining,
            requested_allocated_savings_paise=requested_allocated_savings_paise,
            permitted_allocated_savings_paise=permitted_allocation,
            is_allocation_capped=is_capped,
            allocation_capping_note=capping_note,
            net_funding_gap_paise=funding_gap,
            required_monthly_savings_paise=required_monthly_savings,
            baseline_monthly_surplus_paise=None,
            monthly_discretionary_spend_paise=None,
            feasibility_status=FeasibilityStatus.INSUFFICIENT_DATA,
            monthly_shortfall_paise=None,
            required_discretionary_cut_paise=None,
            months_needed_at_current_surplus=None,
            missing_baseline_inputs=missing_inputs,
            actionable_insight=insight,
            timeline_basis=timeline_basis,
        )

    # 8. Complete Profile Evaluation
    income = p.monthly_take_home_income_paise  # type: ignore[assignment]
    fixed = p.monthly_fixed_commitments_paise  # type: ignore[assignment]
    living = p.monthly_estimated_living_expenses_paise  # type: ignore[assignment]
    disc = p.monthly_estimated_discretionary_paise  # type: ignore[assignment]

    baseline_surplus = income - (fixed + living + disc)

    # Feasibility Decision Tree
    if funding_gap == 0:
        status = FeasibilityStatus.FEASIBLE
        shortfall = 0
        required_cut: Optional[int] = 0
        months_needed: Optional[int] = 0
        insight = (
            "Your goal is fully funded upfront by permitted savings allocation. "
            "No monthly savings are required."
        )

    elif required_monthly_savings <= baseline_surplus:
        status = FeasibilityStatus.FEASIBLE
        shortfall = 0
        required_cut = 0
        buffer_paise = baseline_surplus - required_monthly_savings
        # Estimated months needed assuming constant surplus; baseline_surplus > 0 guaranteed here
        months_needed = ceil_div(funding_gap, baseline_surplus)
        insight = (
            f"Your goal is feasible. Your baseline monthly surplus of {format_inr(baseline_surplus)} "
            f"covers the required {format_inr(required_monthly_savings)}/month, leaving a "
            f"buffer of {format_inr(buffer_paise)}/month."
        )

    elif required_monthly_savings <= baseline_surplus + disc:
        status = FeasibilityStatus.STRETCH_FEASIBLE
        shortfall = 0
        required_cut = required_monthly_savings - baseline_surplus
        # Estimated months needed assuming constant surplus; None when surplus <= 0
        months_needed = ceil_div(funding_gap, baseline_surplus) if baseline_surplus > 0 else None
        remaining_disc = disc - required_cut
        insight = (
            f"Your goal is achievable with adjustments. Required savings ({format_inr(required_monthly_savings)}/mo) "
            f"exceed baseline surplus ({_format_signed_inr(baseline_surplus)}/mo), but can be met by reducing discretionary "
            f"spending by {format_inr(required_cut)}/month (from {format_inr(disc)} to {format_inr(remaining_disc)})."
        )

    else:
        status = FeasibilityStatus.INFEASIBLE
        shortfall = required_monthly_savings - (baseline_surplus + disc)
        required_cut = None
        # Estimated months needed assuming constant surplus; None when surplus <= 0
        months_needed = ceil_div(funding_gap, baseline_surplus) if baseline_surplus > 0 else None
        insight = (
            f"Even eliminating 100% of discretionary spending ({format_inr(disc)}/mo) leaves a monthly shortfall "
            f"of {format_inr(shortfall)}/month. Consider extending the target date or adjusting the goal amount."
        )

    return FeasibilityResult(
        goal_id=goal_id,
        title=title,
        target_amount_paise=target_amount_paise,
        target_date=target_date,
        months_remaining=months_remaining,
        requested_allocated_savings_paise=requested_allocated_savings_paise,
        permitted_allocated_savings_paise=permitted_allocation,
        is_allocation_capped=is_capped,
        allocation_capping_note=capping_note,
        net_funding_gap_paise=funding_gap,
        required_monthly_savings_paise=required_monthly_savings,
        baseline_monthly_surplus_paise=baseline_surplus,
        monthly_discretionary_spend_paise=disc,
        feasibility_status=status,
        monthly_shortfall_paise=shortfall,
        required_discretionary_cut_paise=required_cut,
        months_needed_at_current_surplus=months_needed,
        missing_baseline_inputs=[],
        actionable_insight=insight,
        timeline_basis=timeline_basis,
    )
