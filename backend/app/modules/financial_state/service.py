"""Pure derivations over a user's financial state (no HTTP here)."""

from dataclasses import dataclass, field
from typing import List, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.calc.normalize import monthly_equivalent_paise, ratio_bps
from app.modules.financial_state import models as m
from app.modules.financial_state.enums import (
    CoverSource, ExpenseBucket, LiabilityType, Liquidity, OnboardingStep, PolicyType,
)
from app.modules.financial_state.schemas import FinancialSummary, OnboardingStatus, OnboardingStepStatus

# Product assumption (to be reviewed with the finance reviewer): debt at or above this
# rate, or any credit-card balance, is flagged as high-cost.
HIGH_COST_RATE_BPS = 1400
LIQUID = {Liquidity.IMMEDIATE.value, Liquidity.SHORT_TERM.value}
LIFE_POLICIES = {PolicyType.TERM_LIFE.value, PolicyType.OTHER_LIFE.value}


@dataclass
class FinancialState:
    members: Sequence[m.HouseholdMember] = field(default_factory=list)
    incomes: Sequence[m.IncomeStream] = field(default_factory=list)
    expenses: Sequence[m.Expense] = field(default_factory=list)
    assets: Sequence[m.Asset] = field(default_factory=list)
    liabilities: Sequence[m.Liability] = field(default_factory=list)
    policies: Sequence[m.InsurancePolicy] = field(default_factory=list)


def load_state(db: Session, user_id: str) -> FinancialState:
    def rows(model):
        return list(db.scalars(select(model).where(model.user_id == user_id)))

    return FinancialState(
        members=rows(m.HouseholdMember),
        incomes=rows(m.IncomeStream),
        expenses=rows(m.Expense),
        assets=rows(m.Asset),
        liabilities=rows(m.Liability),
        policies=rows(m.InsurancePolicy),
    )


def compute_summary(state: FinancialState) -> FinancialSummary:
    income = sum(monthly_equivalent_paise(i.amount_paise, i.frequency) for i in state.incomes if i.is_active)
    essential = sum(
        monthly_equivalent_paise(e.amount_paise, e.frequency)
        for e in state.expenses if e.bucket == ExpenseBucket.ESSENTIAL.value
    )
    discretionary = sum(
        monthly_equivalent_paise(e.amount_paise, e.frequency)
        for e in state.expenses if e.bucket == ExpenseBucket.DISCRETIONARY.value
    )
    premiums = sum(
        monthly_equivalent_paise(p.annual_premium_paise, "yearly")
        for p in state.policies if p.source == CoverSource.PERSONAL.value
    )
    emi = sum(lia.emi_paise for lia in state.liabilities)
    surplus = income - essential - discretionary - premiums - emi
    investments = sum(a.monthly_contribution_paise for a in state.assets)

    total_assets = sum(a.current_value_paise for a in state.assets)
    liquid = sum(a.current_value_paise for a in state.assets if a.liquidity in LIQUID)
    emergency = sum(a.current_value_paise for a in state.assets if a.is_emergency_fund)
    total_liabilities = sum(lia.outstanding_paise for lia in state.liabilities)
    high_cost = sum(
        lia.outstanding_paise for lia in state.liabilities
        if lia.liability_type == LiabilityType.CREDIT_CARD.value
        or (lia.interest_rate_bps is not None and lia.interest_rate_bps >= HIGH_COST_RATE_BPS)
    )

    obligations = essential + premiums + emi
    runway = round(liquid / obligations, 1) if obligations > 0 else None

    notes: List[str] = []
    if income == 0:
        notes.append("No active income recorded; ratios are unavailable.")
    if not state.expenses:
        notes.append("No expenses recorded; surplus is overstated until spending is added.")
    if emergency and any(a.is_emergency_fund and a.liquidity not in LIQUID for a in state.assets):
        notes.append("Part of the emergency fund is not in an immediately usable asset.")
    if investments > max(surplus, 0):
        notes.append("Planned monthly investments exceed the monthly surplus.")

    return FinancialSummary(
        monthly_income_paise=income,
        monthly_essential_expenses_paise=essential,
        monthly_discretionary_expenses_paise=discretionary,
        monthly_insurance_premiums_paise=premiums,
        monthly_emi_paise=emi,
        monthly_surplus_paise=surplus,
        monthly_planned_investments_paise=investments,
        monthly_unallocated_paise=surplus - investments,
        savings_rate_bps=ratio_bps(surplus, income),
        total_assets_paise=total_assets,
        liquid_assets_paise=liquid,
        emergency_fund_paise=emergency,
        total_liabilities_paise=total_liabilities,
        high_cost_debt_paise=high_cost,
        net_worth_paise=total_assets - total_liabilities,
        emergency_runway_months=runway,
        debt_to_income_bps=ratio_bps(emi, income),
        health_cover_paise=sum(p.cover_amount_paise for p in state.policies if p.policy_type == PolicyType.HEALTH.value),
        life_cover_paise=sum(p.cover_amount_paise for p in state.policies if p.policy_type in LIFE_POLICIES),
        dependents_count=sum(1 for mem in state.members if mem.is_dependent),
        notes=notes,
    )


_STEP_MODELS = {
    OnboardingStep.INCOME: m.IncomeStream,
    OnboardingStep.EXPENSES: m.Expense,
    OnboardingStep.ASSETS: m.Asset,
    OnboardingStep.LIABILITIES: m.Liability,
    OnboardingStep.INSURANCE: m.InsurancePolicy,
}


def onboarding_status(db: Session, user_id: str) -> OnboardingStatus:
    state = db.get(m.OnboardingState, user_id)
    marked = set(state.completed_steps) if state else set()
    profile = db.get(m.HouseholdProfile, user_id)
    profile_done = bool(
        profile and profile.date_of_birth and profile.retirement_age and profile.employment_type
    )

    steps: List[OnboardingStepStatus] = []
    for step in OnboardingStep:
        if step is OnboardingStep.PROFILE:
            count = 1 if profile else 0
            done = profile_done
        else:
            model = _STEP_MODELS[step]
            count = db.scalar(select(func.count()).select_from(model).where(model.user_id == user_id)) or 0
            done = step.value in marked
        steps.append(OnboardingStepStatus(step=step, completed=done, item_count=count))

    completed = sum(s.completed for s in steps)
    next_step = next((s.step for s in steps if not s.completed), None)
    return OnboardingStatus(
        steps=steps, completed_count=completed, total_count=len(steps),
        is_complete=completed == len(steps), next_step=next_step,
    )
