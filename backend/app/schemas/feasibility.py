"""Pydantic schemas for Goal Feasibility API responses."""

from datetime import date
from typing import List, Optional
from pydantic import BaseModel, ConfigDict

from app.domain.feasibility import FeasibilityResult


class TimelineBasisResponse(BaseModel):
    """Schema for calendar-month timeline explanation."""

    current_month: str
    target_month: str
    saving_cycles_count: int
    explanation: str

    model_config = ConfigDict(from_attributes=True)


class GoalFeasibilityResponse(BaseModel):
    """Comprehensive response for goal feasibility evaluation."""

    goal_id: Optional[str] = None
    title: str
    target_amount_paise: int
    target_date: date
    months_remaining: int
    requested_allocated_savings_paise: int
    permitted_allocated_savings_paise: Optional[int] = None
    is_allocation_capped: bool = False
    allocation_capping_note: Optional[str] = None
    net_funding_gap_paise: Optional[int] = None
    required_monthly_savings_paise: Optional[int] = None
    baseline_monthly_surplus_paise: Optional[int] = None
    monthly_discretionary_spend_paise: Optional[int] = None
    feasibility_status: str
    monthly_shortfall_paise: Optional[int] = None
    required_discretionary_cut_paise: Optional[int] = None
    months_needed_at_current_surplus: Optional[int] = None
    monthly_buffer_paise: Optional[int] = None
    missing_baseline_inputs: List[str] = []
    actionable_insight: str
    timeline_basis: TimelineBasisResponse

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_domain_result(cls, result: FeasibilityResult) -> "GoalFeasibilityResponse":
        return cls(
            goal_id=result.goal_id,
            title=result.title,
            target_amount_paise=result.target_amount_paise,
            target_date=result.target_date,
            months_remaining=result.months_remaining,
            requested_allocated_savings_paise=result.requested_allocated_savings_paise,
            permitted_allocated_savings_paise=result.permitted_allocated_savings_paise,
            is_allocation_capped=result.is_allocation_capped,
            allocation_capping_note=result.allocation_capping_note,
            net_funding_gap_paise=result.net_funding_gap_paise,
            required_monthly_savings_paise=result.required_monthly_savings_paise,
            baseline_monthly_surplus_paise=result.baseline_monthly_surplus_paise,
            monthly_discretionary_spend_paise=result.monthly_discretionary_spend_paise,
            feasibility_status=result.feasibility_status.value,
            monthly_shortfall_paise=result.monthly_shortfall_paise,
            required_discretionary_cut_paise=result.required_discretionary_cut_paise,
            months_needed_at_current_surplus=result.months_needed_at_current_surplus,
            monthly_buffer_paise=result.monthly_buffer_paise,
            missing_baseline_inputs=list(result.missing_baseline_inputs),
            actionable_insight=result.actionable_insight,
            timeline_basis=TimelineBasisResponse(
                current_month=result.timeline_basis.current_month,
                target_month=result.timeline_basis.target_month,
                saving_cycles_count=result.timeline_basis.saving_cycles_count,
                explanation=result.timeline_basis.explanation,
            ),
        )
