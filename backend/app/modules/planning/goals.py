"""Goal engine (spec §6.7). Pure functions over plain inputs; the router feeds them."""

from dataclasses import dataclass, replace
from datetime import date
from typing import List, Optional, Sequence

from app.calc.finance import MAX_MONTHS, corpus_for_expenses, emi, future_value, inflate, months_to_reach, required_monthly
from app.calc.normalize import ratio_bps
from app.modules.planning.assumptions import DEFAULT, Assumptions
from app.modules.planning.schemas import GoalAllocation, GoalEvaluation, GoalsPlan, HomeLoanView, RetirementView
from app.calc.normalize import inr_text

PRIORITY_ORDER = {"essential": 0, "important": 1, "aspirational": 2}


@dataclass(frozen=True)
class GoalInput:
    name: str
    goal_type: str
    priority: str
    status: str = "active"
    target_date: Optional[date] = None
    current_cost_paise: Optional[int] = None
    saved_paise: int = 0
    monthly_contribution_paise: int = 0
    inflation_bps: Optional[int] = None
    expected_return_bps: Optional[int] = None
    down_payment_bps: Optional[int] = None
    goal_id: Optional[str] = None


@dataclass(frozen=True)
class PlanContext:
    today: date
    date_of_birth: Optional[date]
    retirement_age: Optional[int]
    monthly_income_paise: int
    monthly_spend_paise: int  # essential + discretionary + premiums (today's money)
    monthly_surplus_paise: int


def months_between(start: date, end: date) -> int:
    """Whole calendar months from start to end (negative if end is earlier)."""
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return months


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    for day in (d.day, 30, 29, 28):
        try:
            return date(year, month, day)
        except ValueError:
            continue
    raise ValueError("unreachable")


def _span(months: int) -> str:
    years, rest = divmod(months, 12)
    parts = ([f"{years} year{'s' if years != 1 else ''}"] if years else []) + ([f"{rest} month{'s' if rest != 1 else ''}"] if rest else [])
    return " ".join(parts) or "0 months"


def _status(projected: int, target: int, a: Assumptions) -> str:
    if target <= 0:
        return "on_track"
    ratio = projected * 10000 // target
    if ratio >= a.on_track_bps:
        return "on_track"
    if ratio >= a.at_risk_bps:
        return "at_risk"
    return "off_track"


def evaluate_goal(g: GoalInput, ctx: PlanContext, a: Assumptions = DEFAULT) -> GoalEvaluation:
    inflation = g.inflation_bps if g.inflation_bps is not None else a.inflation_for(g.goal_type)
    messages: List[str] = []
    base = dict(
        goal_id=g.goal_id, name=g.name, goal_type=g.goal_type, priority=g.priority, goal_status=g.status,
        inflation_bps=inflation, saved_paise=g.saved_paise, current_monthly_paise=g.monthly_contribution_paise,
        cost_today_paise=g.current_cost_paise,
    )

    def needs_info(msg: str, return_bps: int = 0) -> GoalEvaluation:
        return GoalEvaluation(**base, status="needs_info", return_bps=return_bps, messages=[msg])

    # ---- when, and what must be accumulated by then
    retirement_view: Optional[RetirementView] = None
    home_view: Optional[HomeLoanView] = None
    if g.goal_type == "retirement":
        if not ctx.date_of_birth or not ctx.retirement_age:
            return needs_info("Add your date of birth and retirement age in your profile to plan retirement.")
        target_date = add_months(ctx.date_of_birth, ctx.retirement_age * 12)
        months_left = months_between(ctx.today, target_date)
        if months_left <= 0:
            return needs_info("Your retirement age is in the past; update it in your profile.")
        spend_today = g.current_cost_paise if g.current_cost_paise else ctx.monthly_spend_paise
        if not spend_today:
            return needs_info("Add your monthly spending (or a retirement budget) to size the retirement corpus.")
        years_retired = max(1, a.life_expectancy_years - ctx.retirement_age)
        spend_then = inflate(spend_today, inflation, min(months_left, MAX_MONTHS))
        target = corpus_for_expenses(spend_then, a.post_retirement_return_bps, inflation, min(years_retired * 12, MAX_MONTHS))
        future_cost = target
        retirement_view = RetirementView(
            retirement_date=target_date, retirement_age=ctx.retirement_age, years_in_retirement=years_retired,
            monthly_spend_today_paise=spend_today, monthly_spend_at_retirement_paise=spend_then,
            post_retirement_return_bps=a.post_retirement_return_bps,
        )
        base["cost_today_paise"] = spend_today
    else:
        if g.target_date is None:
            return needs_info("Pick a target date for this goal.")
        if not g.current_cost_paise:
            return needs_info("Add what this goal would cost in today's money.")
        target_date = g.target_date
        months_left = months_between(ctx.today, target_date)
        future_cost = inflate(g.current_cost_paise, inflation, max(0, min(months_left, MAX_MONTHS)))
        target = future_cost
        if g.goal_type == "home":
            dp_bps = g.down_payment_bps if g.down_payment_bps is not None else a.home_down_payment_bps
            down = future_cost * dp_bps // 10000
            extra = future_cost * a.home_extra_costs_bps // 10000
            loan = future_cost - down
            loan_emi = emi(loan, a.home_loan_rate_bps, a.home_loan_months) if loan else 0
            emi_ratio = ratio_bps(loan_emi, ctx.monthly_income_paise)
            affordable = None if emi_ratio is None else emi_ratio <= a.home_emi_to_income_limit_bps
            home_view = HomeLoanView(
                price_at_purchase_paise=future_cost, down_payment_paise=down, extra_costs_paise=extra, loan_paise=loan,
                loan_rate_bps=a.home_loan_rate_bps, loan_months=a.home_loan_months, emi_paise=loan_emi,
                emi_to_income_bps=emi_ratio, affordable=affordable,
            )
            target = down + extra
            if affordable is False:
                messages.append(
                    f"The home-loan EMI would be {emi_ratio / 100:.0f}% of today's take-home pay; "
                    f"above {a.home_emi_to_income_limit_bps / 100:.0f}% is a stretch. "
                    "Consider a larger down payment, a lower budget or a later date."
                )

    return_bps = g.expected_return_bps if g.expected_return_bps is not None else a.return_for_months(max(months_left, 0))
    base.update(target_date=target_date, months_left=months_left, return_bps=return_bps,
                future_cost_paise=future_cost, savings_target_paise=target,
                home_loan=home_view, retirement=retirement_view)

    if g.status == "achieved":
        return GoalEvaluation(**base, status="achieved", projected_paise=target, funded_bps=10000,
                              required_monthly_paise=0, monthly_gap_paise=0, messages=messages)

    horizon = max(0, min(months_left, MAX_MONTHS))
    projected = future_value(g.saved_paise, g.monthly_contribution_paise, return_bps, horizon)
    if months_left <= 0:
        required = 0 if g.saved_paise >= target else None
        if required is None:
            messages.append("The target date has passed and the goal is not funded. Move the date or mark it achieved.")
    else:
        required = required_monthly(target, g.saved_paise, return_bps, horizon)
    gap = None if required is None else max(0, required - g.monthly_contribution_paise)
    reach = months_to_reach(target, g.saved_paise, g.monthly_contribution_paise, return_bps)
    status = _status(projected, target, a) if months_left > 0 else ("on_track" if g.saved_paise >= target else "off_track")

    if status != "on_track" and gap:
        messages.append(f"Add about {inr_text(gap)} a month to stay on track.")
    if status != "on_track" and reach is not None and months_left > 0 and reach > months_left:
        messages.append(f"At the current pace this goal is reached about {_span(reach - months_left)} late.")

    return GoalEvaluation(
        **base, status=status, projected_paise=projected, funded_bps=ratio_bps(projected, target) if target else 10000,
        required_monthly_paise=required, monthly_gap_paise=gap, months_to_reach_at_current=reach,
        reach_date_at_current=add_months(ctx.today, reach) if reach is not None else None, messages=messages,
    )


def plan_goals(goals: Sequence[GoalInput], ctx: PlanContext, a: Assumptions = DEFAULT) -> GoalsPlan:
    evaluations = [evaluate_goal(g, ctx, a) for g in goals]
    active = [
        (g, e) for g, e in zip(goals, evaluations)
        if g.status == "active" and e.required_monthly_paise is not None and e.status != "achieved"
    ]
    active.sort(key=lambda ge: (PRIORITY_ORDER.get(ge[0].priority, 9), ge[1].target_date or date.max))

    available = max(0, ctx.monthly_surplus_paise)
    remaining = available
    allocation: List[GoalAllocation] = []
    for g, e in active:
        need = e.required_monthly_paise or 0
        give = min(need, remaining)
        remaining -= give
        allocation.append(GoalAllocation(goal_id=g.goal_id or "", name=g.name, priority=g.priority,
                                         required_monthly_paise=need, allocated_paise=give, fully_funded=give >= need))

    total_required = sum(x.required_monthly_paise for x in allocation)
    total_current = sum(g.monthly_contribution_paise for g, _ in active)
    counts = {s: sum(1 for e in evaluations if e.status == s)
              for s in ("on_track", "at_risk", "off_track", "achieved", "needs_info")}

    messages: List[str] = []
    if ctx.monthly_surplus_paise <= 0:
        messages.append("Your monthly spending, EMIs and premiums use all your income, so no goal can be funded yet.")
    elif total_required > available:
        first_short = next((x for x in allocation if not x.fully_funded), None)
        messages.append(
            f"Your goals need {inr_text(total_required)} a month but your surplus is {inr_text(available)}. "
            + (f"Funding by priority, '{first_short.name}' is the first goal left short." if first_short else "")
        )
    if total_current > available > 0:
        messages.append("You have assigned more monthly money to goals than your surplus. Check the amounts.")

    return GoalsPlan(
        goals=evaluations, allocation=allocation, monthly_surplus_paise=ctx.monthly_surplus_paise,
        total_required_monthly_paise=total_required, total_current_monthly_paise=total_current,
        unfunded_monthly_paise=max(0, total_required - available), counts=counts,
        assumptions=a.describe(), messages=messages,
    )


def with_overrides(g: GoalInput, **overrides) -> GoalInput:
    clean = {k: v for k, v in overrides.items() if v is not None and hasattr(g, k)}
    return replace(g, **clean)
