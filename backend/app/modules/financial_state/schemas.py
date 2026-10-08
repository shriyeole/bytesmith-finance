"""Request/response schemas for M1.

Money crosses the API only as integer paise (strict ints: floats, strings and booleans
are rejected). Rates are integer basis points. The frontend converts rupees <-> paise.
"""

from datetime import date, datetime
from typing import Annotated, List, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.calc.normalize import monthly_equivalent_paise
from app.modules.financial_state.enums import (
    AssetType, CoverSource, EmploymentType, ExpenseBucket, ExpenseCategory, Frequency, IncomeKind,
    IncomeStability, LiabilityType, Liquidity, MaritalStatus, OnboardingStep, Owner, PolicyType,
    Relationship, TaxRegime,
)

MAX_PAISE = 10**15  # ₹10 lakh crore — far above any household figure, guards typos/overflow

Paise = Annotated[int, Field(ge=0, le=MAX_PAISE, strict=True)]
Bps = Annotated[int, Field(ge=0, le=10000, strict=True)]
GrowthBps = Annotated[int, Field(ge=-5000, le=10000, strict=True)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _age_on(dob: date, on: date) -> int:
    return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))


# ---------------------------------------------------------------- household profile
class HouseholdProfileUpdate(_In):
    """Partial upsert: omitted fields keep their value, explicit null clears."""

    full_name: Optional[Name] = None
    date_of_birth: Optional[date] = None
    marital_status: Optional[MaritalStatus] = None
    city: Optional[ShortText] = None
    retirement_age: Optional[Annotated[int, Field(ge=30, le=85, strict=True)]] = None
    employment_type: Optional[EmploymentType] = None
    income_stability: Optional[IncomeStability] = None
    tax_regime: Optional[TaxRegime] = None

    @model_validator(mode="after")
    def _check_dates(self):
        if self.date_of_birth is not None:
            age = _age_on(self.date_of_birth, date.today())
            if age < 18 or age > 100:
                raise ValueError("date_of_birth must give an age between 18 and 100.")
            if self.retirement_age is not None and self.retirement_age <= age:
                raise ValueError("retirement_age must be greater than current age.")
        return self


class HouseholdProfileRead(_Out):
    full_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    age: Optional[int] = None
    marital_status: Optional[str] = None
    city: Optional[str] = None
    retirement_age: Optional[int] = None
    years_to_retirement: Optional[int] = None
    employment_type: Optional[str] = None
    income_stability: Optional[str] = None
    tax_regime: str = "unknown"
    updated_at: Optional[datetime] = None

    @model_validator(mode="after")
    def _derive(self):
        if self.date_of_birth:
            self.age = _age_on(self.date_of_birth, date.today())
            if self.retirement_age:
                self.years_to_retirement = max(0, self.retirement_age - self.age)
        return self


# ---------------------------------------------------------------- members
class MemberCreate(_In):
    name: Name
    relationship: Relationship
    date_of_birth: Optional[date] = None
    is_dependent: bool = True

    @model_validator(mode="after")
    def _dob(self):
        if self.date_of_birth and self.date_of_birth > date.today():
            raise ValueError("date_of_birth cannot be in the future.")
        return self


class MemberUpdate(_In):
    name: Optional[Name] = None
    relationship: Optional[Relationship] = None
    date_of_birth: Optional[date] = None
    is_dependent: Optional[bool] = None


class MemberRead(_Out):
    id: str
    name: str
    relationship: str
    date_of_birth: Optional[date] = None
    is_dependent: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------- income
class IncomeCreate(_In):
    name: Name
    kind: IncomeKind
    owner: Owner = Owner.SELF
    amount_paise: Paise
    frequency: Frequency = Frequency.MONTHLY
    is_net_of_tax: bool = True
    expected_growth_bps: Optional[GrowthBps] = None
    is_active: bool = True


class IncomeUpdate(_In):
    name: Optional[Name] = None
    kind: Optional[IncomeKind] = None
    owner: Optional[Owner] = None
    amount_paise: Optional[Paise] = None
    frequency: Optional[Frequency] = None
    is_net_of_tax: Optional[bool] = None
    expected_growth_bps: Optional[GrowthBps] = None
    is_active: Optional[bool] = None


class IncomeRead(_Out):
    id: str
    name: str
    kind: str
    owner: str
    amount_paise: int
    frequency: str
    is_net_of_tax: bool
    expected_growth_bps: Optional[int] = None
    is_active: bool
    monthly_equivalent_paise: int = 0
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _monthly(self):
        self.monthly_equivalent_paise = monthly_equivalent_paise(self.amount_paise, self.frequency) if self.is_active else 0
        return self


# ---------------------------------------------------------------- expenses
class ExpenseCreate(_In):
    name: Name
    category: ExpenseCategory
    bucket: Optional[ExpenseBucket] = None  # defaults from category
    amount_paise: Paise
    frequency: Frequency = Frequency.MONTHLY
    inflation_bps: Optional[Annotated[int, Field(ge=0, le=5000, strict=True)]] = None


class ExpenseUpdate(_In):
    name: Optional[Name] = None
    category: Optional[ExpenseCategory] = None
    bucket: Optional[ExpenseBucket] = None
    amount_paise: Optional[Paise] = None
    frequency: Optional[Frequency] = None
    inflation_bps: Optional[Annotated[int, Field(ge=0, le=5000, strict=True)]] = None


class ExpenseRead(_Out):
    id: str
    name: str
    category: str
    bucket: str
    amount_paise: int
    frequency: str
    inflation_bps: Optional[int] = None
    monthly_equivalent_paise: int = 0
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _monthly(self):
        self.monthly_equivalent_paise = monthly_equivalent_paise(self.amount_paise, self.frequency)
        return self


# ---------------------------------------------------------------- assets
class AssetCreate(_In):
    name: Name
    asset_type: AssetType
    owner: Owner = Owner.SELF
    current_value_paise: Paise
    liquidity: Optional[Liquidity] = None  # defaults from asset_type
    is_emergency_fund: bool = False
    monthly_contribution_paise: Paise = 0
    value_as_of: Optional[date] = None


class AssetUpdate(_In):
    name: Optional[Name] = None
    asset_type: Optional[AssetType] = None
    owner: Optional[Owner] = None
    current_value_paise: Optional[Paise] = None
    liquidity: Optional[Liquidity] = None
    is_emergency_fund: Optional[bool] = None
    monthly_contribution_paise: Optional[Paise] = None
    value_as_of: Optional[date] = None


class AssetRead(_Out):
    id: str
    name: str
    asset_type: str
    owner: str
    current_value_paise: int
    liquidity: str
    is_emergency_fund: bool
    monthly_contribution_paise: int
    value_as_of: Optional[date] = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------- liabilities
class LiabilityCreate(_In):
    name: Name
    liability_type: LiabilityType
    lender: Optional[ShortText] = None
    outstanding_paise: Paise
    interest_rate_bps: Optional[Annotated[int, Field(ge=0, le=6000, strict=True)]] = None
    emi_paise: Paise = 0
    remaining_months: Optional[Annotated[int, Field(ge=0, le=600, strict=True)]] = None


class LiabilityUpdate(_In):
    name: Optional[Name] = None
    liability_type: Optional[LiabilityType] = None
    lender: Optional[ShortText] = None
    outstanding_paise: Optional[Paise] = None
    interest_rate_bps: Optional[Annotated[int, Field(ge=0, le=6000, strict=True)]] = None
    emi_paise: Optional[Paise] = None
    remaining_months: Optional[Annotated[int, Field(ge=0, le=600, strict=True)]] = None


class LiabilityRead(_Out):
    id: str
    name: str
    liability_type: str
    lender: Optional[str] = None
    outstanding_paise: int
    interest_rate_bps: Optional[int] = None
    emi_paise: int
    remaining_months: Optional[int] = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------- insurance
class PolicyCreate(_In):
    policy_type: PolicyType
    provider: Optional[ShortText] = None
    covers: ShortText = "self"
    source: CoverSource = CoverSource.PERSONAL
    cover_amount_paise: Paise
    annual_premium_paise: Paise = 0
    renewal_date: Optional[date] = None


class PolicyUpdate(_In):
    policy_type: Optional[PolicyType] = None
    provider: Optional[ShortText] = None
    covers: Optional[ShortText] = None
    source: Optional[CoverSource] = None
    cover_amount_paise: Optional[Paise] = None
    annual_premium_paise: Optional[Paise] = None
    renewal_date: Optional[date] = None


class PolicyRead(_Out):
    id: str
    policy_type: str
    provider: Optional[str] = None
    covers: str
    source: str
    cover_amount_paise: int
    annual_premium_paise: int
    renewal_date: Optional[date] = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------- summary & onboarding
class FinancialSummary(BaseModel):
    """Derived current position. Every figure is reproducible from the stored rows."""

    monthly_income_paise: int
    monthly_essential_expenses_paise: int
    monthly_discretionary_expenses_paise: int
    monthly_insurance_premiums_paise: int
    monthly_emi_paise: int
    monthly_surplus_paise: int  # income − expenses − premiums − EMIs (may be negative)
    monthly_planned_investments_paise: int
    monthly_unallocated_paise: int  # surplus − planned investments (may be negative)
    savings_rate_bps: Optional[int] = None  # surplus / income
    total_assets_paise: int
    liquid_assets_paise: int
    emergency_fund_paise: int
    total_liabilities_paise: int
    high_cost_debt_paise: int
    net_worth_paise: int
    emergency_runway_months: Optional[float] = None  # liquid assets / (essentials + premiums + EMIs)
    debt_to_income_bps: Optional[int] = None  # EMIs / income
    health_cover_paise: int
    life_cover_paise: int
    dependents_count: int
    notes: List[str]


class OnboardingStatus(BaseModel):
    steps: List["OnboardingStepStatus"]
    completed_count: int
    total_count: int
    is_complete: bool
    next_step: Optional[OnboardingStep] = None


class OnboardingStepStatus(BaseModel):
    step: OnboardingStep
    completed: bool
    item_count: int


OnboardingStatus.model_rebuild()
