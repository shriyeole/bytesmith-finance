from datetime import date, datetime
from enum import Enum
from typing import Annotated, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.modules.financial_state.schemas import Paise

Bps30 = Annotated[int, Field(ge=0, le=3000, strict=True)]
Pct = Annotated[int, Field(ge=0, le=10000, strict=True)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class GoalType(str, Enum):
    RETIREMENT = "retirement"
    HOME = "home"
    CAR = "car"
    CHILD_EDUCATION = "child_education"
    WEDDING = "wedding"
    TRAVEL = "travel"
    BIG_PURCHASE = "big_purchase"
    OTHER = "other"


class Priority(str, Enum):
    ESSENTIAL = "essential"
    IMPORTANT = "important"
    ASPIRATIONAL = "aspirational"


class GoalStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ACHIEVED = "achieved"


DEFAULT_PRIORITY = {
    GoalType.RETIREMENT: Priority.ESSENTIAL,
    GoalType.CHILD_EDUCATION: Priority.ESSENTIAL,
    GoalType.HOME: Priority.IMPORTANT,
    GoalType.WEDDING: Priority.IMPORTANT,
    GoalType.OTHER: Priority.IMPORTANT,
    GoalType.CAR: Priority.ASPIRATIONAL,
    GoalType.TRAVEL: Priority.ASPIRATIONAL,
    GoalType.BIG_PURCHASE: Priority.ASPIRATIONAL,
}


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GoalCreate(_In):
    name: Name
    goal_type: GoalType
    priority: Optional[Priority] = None  # defaults by type
    target_date: Optional[date] = None   # required except for retirement
    current_cost_paise: Optional[Paise] = None
    saved_paise: Paise = 0
    monthly_contribution_paise: Paise = 0
    inflation_bps: Optional[Bps30] = None
    expected_return_bps: Optional[Bps30] = None
    down_payment_bps: Optional[Pct] = None
    notes: Optional[Annotated[str, StringConstraints(max_length=2000)]] = None
    status: GoalStatus = GoalStatus.ACTIVE


class GoalUpdate(_In):
    name: Optional[Name] = None
    goal_type: Optional[GoalType] = None
    priority: Optional[Priority] = None
    target_date: Optional[date] = None
    current_cost_paise: Optional[Paise] = None
    saved_paise: Optional[Paise] = None
    monthly_contribution_paise: Optional[Paise] = None
    inflation_bps: Optional[Bps30] = None
    expected_return_bps: Optional[Bps30] = None
    down_payment_bps: Optional[Pct] = None
    notes: Optional[Annotated[str, StringConstraints(max_length=2000)]] = None
    status: Optional[GoalStatus] = None


class GoalWhatIf(_In):
    """Temporary overrides for one goal; nothing is saved."""

    target_date: Optional[date] = None
    current_cost_paise: Optional[Paise] = None
    saved_paise: Optional[Paise] = None
    monthly_contribution_paise: Optional[Paise] = None
    inflation_bps: Optional[Bps30] = None
    expected_return_bps: Optional[Bps30] = None
    down_payment_bps: Optional[Pct] = None
    retirement_age: Optional[Annotated[int, Field(ge=30, le=85, strict=True)]] = None


class GoalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    goal_type: str
    priority: str
    status: str
    target_date: Optional[date] = None
    current_cost_paise: Optional[int] = None
    saved_paise: int
    monthly_contribution_paise: int
    inflation_bps: Optional[int] = None
    expected_return_bps: Optional[int] = None
    down_payment_bps: Optional[int] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class HomeLoanView(BaseModel):
    price_at_purchase_paise: int
    down_payment_paise: int
    extra_costs_paise: int
    loan_paise: int
    loan_rate_bps: int
    loan_months: int
    emi_paise: int
    emi_to_income_bps: Optional[int] = None
    affordable: Optional[bool] = None


class RetirementView(BaseModel):
    retirement_date: date
    retirement_age: int
    years_in_retirement: int
    monthly_spend_today_paise: int
    monthly_spend_at_retirement_paise: int
    post_retirement_return_bps: int


class GoalEvaluation(BaseModel):
    goal_id: Optional[str] = None
    name: str
    goal_type: str
    priority: str
    goal_status: str
    status: str  # on_track | at_risk | off_track | achieved | needs_info
    target_date: Optional[date] = None
    months_left: Optional[int] = None
    inflation_bps: int
    return_bps: int
    cost_today_paise: Optional[int] = None
    future_cost_paise: Optional[int] = None
    savings_target_paise: Optional[int] = None
    saved_paise: int
    current_monthly_paise: int
    projected_paise: Optional[int] = None
    funded_bps: Optional[int] = None
    required_monthly_paise: Optional[int] = None
    monthly_gap_paise: Optional[int] = None
    months_to_reach_at_current: Optional[int] = None
    reach_date_at_current: Optional[date] = None
    home_loan: Optional[HomeLoanView] = None
    retirement: Optional[RetirementView] = None
    messages: List[str] = []


class GoalAllocation(BaseModel):
    goal_id: str
    name: str
    priority: str
    required_monthly_paise: int
    allocated_paise: int
    fully_funded: bool


class GoalsPlan(BaseModel):
    goals: List[GoalEvaluation]
    allocation: List[GoalAllocation]
    monthly_surplus_paise: int
    total_required_monthly_paise: int
    total_current_monthly_paise: int
    unfunded_monthly_paise: int
    counts: Dict[str, int]
    assumptions: List[str]
    messages: List[str]
