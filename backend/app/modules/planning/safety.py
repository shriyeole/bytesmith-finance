"""Emergency fund, debt and protection engines (spec §6.4-6.6). Each returns its numbers,
a status, and the method in plain words so the UI can always show "how we got this"."""

from datetime import date, timedelta
from typing import List, Optional, Sequence

from pydantic import BaseModel

from app.calc.finance import amortize, future_value, required_monthly
from app.calc.normalize import monthly_equivalent_paise, ratio_bps
from app.modules.financial_state import models as m
from app.modules.financial_state.schemas import FinancialSummary
from app.modules.planning.assumptions import DEFAULT, Assumptions
from app.modules.planning.goals import add_months

LIQUID = {"immediate", "short_term"}
FINANCIAL = {"immediate", "short_term", "market_linked"}


# ---------------------------------------------------------------- emergency fund
class EmergencyFund(BaseModel):
    status: str  # good | attention | critical | needs_info
    monthly_obligations_paise: int
    target_months_low: int
    target_months_high: int
    target_low_paise: int
    target_high_paise: int
    current_paise: int
    uses_flagged_assets: bool
    months_covered: Optional[float] = None
    gap_to_low_paise: int
    gap_to_high_paise: int
    monthly_to_reach_low_in_12m_paise: int
    reasons: List[str]
    method: List[str]


def emergency_fund(summary: FinancialSummary, stability: Optional[str], assets: Sequence[m.Asset],
                   a: Assumptions = DEFAULT) -> EmergencyFund:
    obligations = summary.monthly_essential_expenses_paise + summary.monthly_insurance_premiums_paise + summary.monthly_emi_paise
    low, high = a.emergency_months.get(stability or "stable", a.emergency_months["stable"])
    reasons = [f"Base range {low}–{high} months for {'a ' + stability if stability else 'an assumed stable'} income."]
    if summary.dependents_count:
        low, high = low + 1, high + 1
        reasons.append("+1 month because others depend on your income.")
    if (summary.debt_to_income_bps or 0) > a.debt_to_income_caution_bps:
        low, high = low + 1, high + 1
        reasons.append("+1 month because EMIs take a large share of income.")
    if summary.health_cover_paise == 0:
        low, high = low + 1, high + 1
        reasons.append("+1 month because no health insurance is recorded.")

    flagged = [x for x in assets if x.is_emergency_fund]
    current = sum(x.current_value_paise for x in flagged) if flagged else summary.liquid_assets_paise
    t_low, t_high = obligations * low, obligations * high
    gap_low, gap_high = max(0, t_low - current), max(0, t_high - current)
    covered = round(current / obligations, 1) if obligations else None

    if obligations == 0:
        status = "needs_info"
    elif current >= t_low:
        status = "good"
    elif covered is not None and covered >= 1:
        status = "attention"
    else:
        status = "critical"

    method = [
        "Monthly obligations = essential spending + insurance premiums + loan EMIs.",
        "Target = obligations × months in the range above.",
        "Counts assets you marked as emergency fund; if none are marked, all cash, savings and deposits."
        if flagged else "No asset is marked as emergency fund, so all cash, savings and deposits are counted.",
    ]
    return EmergencyFund(
        status=status, monthly_obligations_paise=obligations, target_months_low=low, target_months_high=high,
        target_low_paise=t_low, target_high_paise=t_high, current_paise=current, uses_flagged_assets=bool(flagged),
        months_covered=covered, gap_to_low_paise=gap_low, gap_to_high_paise=gap_high,
        monthly_to_reach_low_in_12m_paise=required_monthly(t_low, current, 0, 12) if gap_low else 0,
        reasons=reasons, method=method,
    )


# ---------------------------------------------------------------- debt
class LoanView(BaseModel):
    id: str
    name: str
    liability_type: str
    outstanding_paise: int
    interest_rate_bps: Optional[int] = None
    emi_paise: int
    months_left: Optional[int] = None
    payoff_date: Optional[date] = None
    interest_remaining_paise: Optional[int] = None
    high_cost: bool
    notes: List[str]


class DebtOverview(BaseModel):
    status: str  # good | attention | critical | none
    total_outstanding_paise: int
    total_emi_paise: int
    debt_to_income_bps: Optional[int] = None
    high_cost_outstanding_paise: int
    loans: List[LoanView]
    payoff_order: List[str]
    messages: List[str]
    method: List[str]


def _is_high_cost(lia: m.Liability, a: Assumptions) -> bool:
    return lia.liability_type == "credit_card" or (lia.interest_rate_bps or 0) >= a.high_cost_debt_rate_bps


def loan_view(lia: m.Liability, today: date, a: Assumptions = DEFAULT) -> LoanView:
    notes: List[str] = []
    months = interest = None
    if lia.outstanding_paise == 0:
        months, interest = 0, 0
    elif lia.interest_rate_bps is None:
        notes.append("Add the interest rate to see payoff date and interest cost.")
    elif lia.emi_paise == 0:
        if lia.liability_type == "credit_card":
            notes.append("Card balances usually charge 36–48% a year. Clearing it is normally the best use of spare cash.")
        else:
            notes.append("Add the EMI to see the payoff date.")
    else:
        am = amortize(lia.outstanding_paise, lia.interest_rate_bps, lia.emi_paise)
        if am.months is None:
            notes.append("The EMI does not cover the monthly interest, so this balance never reduces.")
        else:
            months, interest = am.months, am.total_interest_paise
            if lia.remaining_months and abs(lia.remaining_months - am.months) > 3:
                notes.append(f"You entered {lia.remaining_months} months left; the balance, rate and EMI imply {am.months}.")
    return LoanView(
        id=lia.id, name=lia.name, liability_type=lia.liability_type, outstanding_paise=lia.outstanding_paise,
        interest_rate_bps=lia.interest_rate_bps, emi_paise=lia.emi_paise, months_left=months,
        payoff_date=add_months(today, months) if months is not None else None,
        interest_remaining_paise=interest, high_cost=_is_high_cost(lia, a), notes=notes,
    )


def debt_overview(liabilities: Sequence[m.Liability], summary: FinancialSummary, today: date,
                  a: Assumptions = DEFAULT) -> DebtOverview:
    loans = [loan_view(x, today, a) for x in liabilities]
    dti = summary.debt_to_income_bps
    high = sum(x.outstanding_paise for x in loans if x.high_cost)
    if not loans:
        status = "none"
    elif high > 0 or (dti or 0) > a.debt_to_income_high_bps:
        status = "critical"
    elif (dti or 0) > a.debt_to_income_caution_bps:
        status = "attention"
    else:
        status = "good"
    messages: List[str] = []
    if dti is not None and dti > a.debt_to_income_high_bps:
        messages.append(f"EMIs take {dti / 100:.0f}% of take-home pay; above {a.debt_to_income_high_bps / 100:.0f}% leaves little room for goals.")
    elif dti is not None and dti > a.debt_to_income_caution_bps:
        messages.append(f"EMIs take {dti / 100:.0f}% of take-home pay; keep new borrowing low.")
    if high:
        messages.append("You have high-cost debt. Paying it down usually beats any investment return.")
    order = [x.id for x in sorted(loans, key=lambda x: (-(x.interest_rate_bps if x.interest_rate_bps is not None else (4200 if x.liability_type == "credit_card" else 0)), x.outstanding_paise)) if x.outstanding_paise > 0]
    return DebtOverview(
        status=status, total_outstanding_paise=sum(x.outstanding_paise for x in loans),
        total_emi_paise=sum(x.emi_paise for x in loans), debt_to_income_bps=dti, high_cost_outstanding_paise=high,
        loans=loans, payoff_order=order, messages=messages,
        method=[
            "Payoff dates simulate each loan month by month: interest on the reducing balance, EMI at month end.",
            f"High-cost = credit cards or rates of {a.high_cost_debt_rate_bps / 100:g}% or more.",
            "Suggested order pays the highest interest rate first (the 'avalanche' method).",
        ],
    )


class PrepayScenario(BaseModel):
    loan_id: str
    lump_sum_paise: int
    extra_monthly_paise: int
    investment_return_bps: int
    base_months: int
    new_months: int
    months_saved: int
    interest_saved_paise: int
    wealth_if_prepay_paise: int
    wealth_if_invest_paise: int
    better_option: str  # prepay | invest | similar
    explanation: List[str]


def prepay_vs_invest(lia: m.Liability, lump_sum: int, extra_monthly: int, a: Assumptions = DEFAULT) -> PrepayScenario:
    """Compare, at the loan's original end date, (A) prepaying then investing the freed EMI,
    versus (B) keeping the loan and investing the same money. Same cash leaves your pocket
    every month in both, so the end wealth is a fair comparison."""
    if lia.interest_rate_bps is None or lia.emi_paise == 0:
        raise ValueError("Loan needs an interest rate and EMI for this comparison.")
    base = amortize(lia.outstanding_paise, lia.interest_rate_bps, lia.emi_paise)
    if base.months is None:
        raise ValueError("The current EMI never clears this loan.")
    new = amortize(lia.outstanding_paise, lia.interest_rate_bps, lia.emi_paise,
                   extra_monthly_paise=extra_monthly, lump_sum_now_paise=min(lump_sum, lia.outstanding_paise))
    assert new.months is not None
    n0, n1 = base.months, new.months
    r = a.return_for_months(n0)
    saved_months = n0 - n1
    # (A) after early payoff, invest EMI + extra every month until the original end date.
    budget = lia.emi_paise + extra_monthly
    wealth_a = future_value(0, budget, r, saved_months)
    # The final payment is usually partial; the unused part of that month's budget is invested too.
    lump_used = min(lump_sum, lia.outstanding_paise)
    leftover = max(0, budget * n1 - ((new.total_paid_paise or 0) - lump_used))
    wealth_a += future_value(leftover, 0, r, saved_months)
    # lump sum larger than the balance: the remainder is invested from day one
    wealth_a += future_value(max(0, lump_sum - lia.outstanding_paise), 0, r, n0)
    # (B) invest the lump sum now and the extra every month for the original tenure
    wealth_b = future_value(lump_sum, extra_monthly, r, n0)
    diff = wealth_a - wealth_b
    threshold = max(wealth_a, wealth_b) // 50  # within 2% counts as similar
    better = "similar" if abs(diff) <= threshold else ("prepay" if diff > 0 else "invest")
    return PrepayScenario(
        loan_id=lia.id, lump_sum_paise=lump_sum, extra_monthly_paise=extra_monthly, investment_return_bps=r,
        base_months=n0, new_months=n1, months_saved=saved_months,
        interest_saved_paise=(base.total_interest_paise or 0) - (new.total_interest_paise or 0),
        wealth_if_prepay_paise=wealth_a, wealth_if_invest_paise=wealth_b, better_option=better,
        explanation=[
            f"Prepaying is a guaranteed {lia.interest_rate_bps / 100:g}% 'return'; investing assumes {r / 100:g}% a year, which is not guaranteed.",
            "Both options cost you the same each month; we compare your wealth on the loan's original end date.",
            "Taxes, prepayment charges and home-loan tax benefits are not included.",
        ],
    )


# ---------------------------------------------------------------- protection
class CoverCheck(BaseModel):
    status: str  # good | attention | critical | not_needed
    recommended_paise: int
    existing_paise: int
    gap_paise: int
    reasons: List[str]


class Renewal(BaseModel):
    policy_id: str
    policy_type: str
    renewal_date: date
    days_left: int


class Protection(BaseModel):
    life: CoverCheck
    health: CoverCheck
    renewals: List[Renewal]
    messages: List[str]
    method: List[str]


def protection(summary: FinancialSummary, incomes: Sequence[m.IncomeStream], members: Sequence[m.HouseholdMember],
               assets: Sequence[m.Asset], policies: Sequence[m.InsurancePolicy], education_gap_paise: int,
               today: date, a: Assumptions = DEFAULT) -> Protection:
    own_income_annual = 12 * sum(
        monthly_equivalent_paise(i.amount_paise, i.frequency) for i in incomes if i.is_active and i.owner == "self"
    )
    dependents = [x for x in members if x.is_dependent]
    financial_assets = sum(x.current_value_paise for x in assets if x.liquidity in FINANCIAL)

    # Life
    life_reasons: List[str] = []
    if dependents:
        need = own_income_annual * a.life_cover_income_multiple + summary.total_liabilities_paise + education_gap_paise
        life_reasons.append(f"{a.life_cover_income_multiple}× your yearly take-home income to replace it for your family.")
        if summary.total_liabilities_paise:
            life_reasons.append("Plus outstanding loans, so they are not left to your family.")
        if education_gap_paise:
            life_reasons.append("Plus the unfunded part of children's education goals.")
        need = max(0, need - financial_assets)
        if financial_assets:
            life_reasons.append("Minus savings and investments your family could use.")
    else:
        need = max(0, summary.total_liabilities_paise - financial_assets)
        life_reasons.append("No dependents recorded, so only loans not covered by your savings need cover.")
    existing_life = summary.life_cover_paise
    life_gap = max(0, need - existing_life)
    life_status = "not_needed" if need == 0 else ("good" if life_gap == 0 else ("attention" if existing_life >= need // 2 else "critical"))

    # Health
    family = bool(dependents) or any(x.relationship == "spouse" for x in members)
    rec_health = a.health_cover_family_paise if family else a.health_cover_single_paise
    health_reasons = [f"Suggested minimum {'family floater' if family else 'individual cover'} of ₹{rec_health // 10_000_000}L."]
    if any(x.relationship == "parent" and x.is_dependent for x in members):
        rec_health += a.health_cover_parents_extra_paise
        health_reasons.append("Plus ₹5L because dependent parents need separate or added cover.")
    personal = sum(p.cover_amount_paise for p in policies if p.policy_type == "health" and p.source == "personal")
    employer = sum(p.cover_amount_paise for p in policies if p.policy_type == "health" and p.source == "employer")
    existing_health = personal + employer
    health_gap = max(0, rec_health - existing_health)
    if existing_health == 0:
        health_status = "critical"
    elif health_gap:
        health_status = "attention"
    else:
        health_status = "good"
    messages: List[str] = []
    if employer and personal < rec_health:
        if health_status == "good":
            health_status = "attention"
        messages.append("Employer health cover ends if you change or lose your job; consider a personal policy too.")

    soon = today + timedelta(days=a.renewal_warning_days)
    renewals = sorted(
        (Renewal(policy_id=p.id, policy_type=p.policy_type, renewal_date=p.renewal_date, days_left=(p.renewal_date - today).days)
         for p in policies if p.renewal_date and p.renewal_date <= soon),
        key=lambda r: r.renewal_date,
    )
    for r in renewals:
        messages.append(f"{r.policy_type.replace('_', ' ').capitalize()} policy {'lapsed' if r.days_left < 0 else 'renews'} "
                        f"{'on' if r.days_left < 0 else 'in ' + str(r.days_left) + ' days on'} {r.renewal_date:%d %b %Y}.")

    return Protection(
        life=CoverCheck(status=life_status, recommended_paise=need, existing_paise=existing_life, gap_paise=life_gap, reasons=life_reasons),
        health=CoverCheck(status=health_status, recommended_paise=rec_health, existing_paise=existing_health, gap_paise=health_gap, reasons=health_reasons),
        renewals=renewals, messages=messages,
        method=[
            "These are rule-of-thumb estimates for guidance, not a recommendation of any policy.",
            "Life need uses only your own income; add your partner's cover separately.",
        ],
    )
