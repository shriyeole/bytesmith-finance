"""Wealth simulation (spec §8, module M8).

A month-by-month household timeline: incomes grow and stop at retirement, spending rises
with inflation, loans amortise, surplus first tops up an emergency cash buffer and the rest
is invested, goals are paid for on their dates, and after retirement spending is drawn from
savings. Annual checkpoints are returned for charts.

Scenarios: base (your assumptions), stress (no raises, higher inflation, lower returns),
upside (faster raises, better returns). What-ifs layer events on top of any scenario.
All maths is Decimal; results are deterministic for the same inputs.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.calc.finance import emi as calc_emi
from app.calc.finance import to_paise
from app.calc.normalize import monthly_equivalent_paise
from app.modules.planning.assumptions import Assumptions
from app.modules.planning.goals import GoalInput, add_months, evaluate_goal, months_between

ONE = Decimal(1)
TEN_K = Decimal(10000)
MAX_SIM_MONTHS = 840          # 70 years
DEFAULT_SIM_MONTHS = 480      # when date of birth is unknown
CONTINUES_AFTER_RETIREMENT = {"rental", "interest_dividend", "pension"}
LIQUID = {"immediate", "short_term"}
INVESTED = {"market_linked", "locked"}


# ---------------------------------------------------------------- what-if input
class CareerBreak(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_in_months: int = Field(0, ge=0, le=600, strict=True)
    months: int = Field(ge=1, le=120, strict=True)


class ExtraGoal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    goal_type: str = Field(pattern="^(car|home|other)$")
    cost_today_paise: int = Field(gt=0, le=10**13, strict=True)
    in_months: int = Field(ge=1, le=600, strict=True)


class ChildEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    in_months: int = Field(0, ge=0, le=240, strict=True)
    monthly_cost_today_paise: Optional[int] = Field(None, ge=0, le=10**10, strict=True)
    education_cost_today_paise: Optional[int] = Field(None, ge=0, le=10**12, strict=True)


class Windfall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    in_months: int = Field(0, ge=0, le=600, strict=True)
    amount_paise: int = Field(gt=0, le=10**13, strict=True)


class WhatIf(BaseModel):
    """Changes layered on a scenario. Every field is optional."""

    model_config = ConfigDict(extra="forbid")
    salary_growth_bps: Optional[int] = Field(None, ge=-2000, le=3000, strict=True)
    inflation_bps: Optional[int] = Field(None, ge=0, le=2000, strict=True)
    return_shift_bps: Optional[int] = Field(None, ge=-1000, le=1000, strict=True)
    spend_change_bps: Optional[int] = Field(None, ge=-10000, le=10000, strict=True)  # on discretionary spending
    retirement_age: Optional[int] = Field(None, ge=30, le=85, strict=True)
    career_break: Optional[CareerBreak] = None
    extra_goals: List[ExtraGoal] = Field(default_factory=list, max_length=5)
    child: Optional[ChildEvent] = None
    windfall: Optional[Windfall] = None


# ---------------------------------------------------------------- outputs
class YearPoint(BaseModel):
    year: int
    month: int
    age: Optional[int] = None
    net_worth_paise: int
    net_worth_real_paise: int
    liquid_paise: int
    invested_paise: int
    property_paise: int
    debt_paise: int
    income_paise: int   # over the past 12 months
    spend_paise: int    # spending + EMIs over the past 12 months


class Milestone(BaseModel):
    month: int
    date: date
    age: Optional[int] = None
    kind: str           # goal | goal_short | loan_closed | retirement | depleted | career_break | child | windfall
    label: str
    amount_paise: Optional[int] = None


class GoalOutcome(BaseModel):
    name: str
    date: date
    cost_paise: int
    funded_paise: int
    fully_funded: bool


class JourneySummary(BaseModel):
    months: int
    net_worth_now_paise: int
    retirement_month: Optional[int] = None
    retirement_age: Optional[int] = None
    net_worth_at_retirement_paise: Optional[int] = None
    net_worth_at_retirement_real_paise: Optional[int] = None
    savings_at_retirement_paise: Optional[int] = None  # liquid + invested
    corpus_needed_paise: Optional[int] = None
    retirement_readiness_bps: Optional[int] = None
    depleted_month: Optional[int] = None
    depleted_age: Optional[int] = None
    money_lasts_to_age: Optional[int] = None
    final_net_worth_paise: int
    final_net_worth_real_paise: int
    goals: List[GoalOutcome]
    goals_fully_funded: int
    goals_total: int


class Journey(BaseModel):
    scenario: str
    label: str
    params: Dict[str, int]
    points: List[YearPoint]
    milestones: List[Milestone]
    summary: JourneySummary


SCENARIO_LABELS = {"base": "Expected", "stress": "Tough times", "upside": "Things go well"}


# ---------------------------------------------------------------- engine
@dataclass
class _Loan:
    name: str
    balance: Decimal
    rate: Decimal  # monthly
    emi: int
    closed: bool = False


@dataclass
class _Outflow:
    month: int
    name: str
    amount: int
    home_price: int = 0
    home_loan: int = 0


@dataclass
class _Params:
    salary_growth_override: Optional[int]
    salary_growth_add: int  # may be negative (stress); growth never goes below 0 from this
    inflation_bps: int
    portfolio_bps: int
    post_retirement_bps: int
    cash_bps: int
    retirement_age: Optional[int]


def _params(a: Assumptions, scenario: str, w: WhatIf) -> _Params:
    p = _Params(
        salary_growth_override=None, salary_growth_add=0, inflation_bps=a.general_inflation_bps,
        portfolio_bps=a.portfolio_return_bps, post_retirement_bps=a.post_retirement_return_bps,
        cash_bps=a.cash_return_bps, retirement_age=None,
    )
    if scenario == "stress":
        p.salary_growth_add = -a.stress_salary_cut_bps
        p.inflation_bps += a.stress_inflation_add_bps
        p.portfolio_bps -= a.stress_return_cut_bps
        p.post_retirement_bps -= a.stress_return_cut_bps
        p.cash_bps = max(0, p.cash_bps - a.stress_return_cut_bps // 2)
    elif scenario == "upside":
        p.salary_growth_add = a.upside_salary_add_bps
        p.portfolio_bps += a.upside_return_add_bps
        p.post_retirement_bps += a.upside_return_add_bps
    if w.salary_growth_bps is not None:
        p.salary_growth_override, p.salary_growth_add = w.salary_growth_bps, 0
    if w.inflation_bps is not None:
        p.inflation_bps = w.inflation_bps
    if w.return_shift_bps:
        p.portfolio_bps += w.return_shift_bps
        p.post_retirement_bps += w.return_shift_bps
    p.portfolio_bps, p.post_retirement_bps = max(0, p.portfolio_bps), max(0, p.post_retirement_bps)
    p.retirement_age = w.retirement_age
    return p


def simulate(inp, scenario: str = "base", what_if: Optional[WhatIf] = None) -> Journey:
    """`inp` is a snapshot.Inputs (kept untyped here to avoid an import cycle)."""
    if scenario not in SCENARIO_LABELS:
        raise ValueError("scenario must be base, stress or upside")
    w = what_if or WhatIf()
    a: Assumptions = inp.assumptions
    p = _params(a, scenario, w)
    today: date = inp.today
    hp = inp.household
    dob = hp.date_of_birth if hp else None
    ret_age = p.retirement_age or (hp.retirement_age if hp else None)

    def age_at(month: int) -> Optional[int]:
        return months_between(dob, add_months(today, month)) // 12 if dob else None

    horizon = DEFAULT_SIM_MONTHS
    if dob:
        horizon = months_between(today, add_months(dob, a.life_expectancy_years * 12))
    horizon = max(12, min(MAX_SIM_MONTHS, horizon))
    ret_month = months_between(today, add_months(dob, ret_age * 12)) if (dob and ret_age) else None
    if ret_month is not None and ret_month <= 0:
        ret_month = 0

    # ---- starting position
    s = inp.state
    incomes = []
    for i in s.incomes:
        if not i.is_active:
            continue
        growth = i.expected_growth_bps if i.expected_growth_bps is not None else a.salary_growth_bps
        if p.salary_growth_override is not None and i.kind not in CONTINUES_AFTER_RETIREMENT:
            growth = p.salary_growth_override
        elif i.kind not in CONTINUES_AFTER_RETIREMENT:
            growth = max(0, growth + p.salary_growth_add) if p.salary_growth_add < 0 else growth + p.salary_growth_add
        incomes.append({"amount": Decimal(monthly_equivalent_paise(i.amount_paise, i.frequency)),
                        "growth": Decimal(growth) / TEN_K, "stops": i.kind not in CONTINUES_AFTER_RETIREMENT})
    essential = Decimal(sum(monthly_equivalent_paise(e.amount_paise, e.frequency) for e in s.expenses if e.bucket == "essential"))
    essential += Decimal(sum(monthly_equivalent_paise(x.annual_premium_paise, "yearly") for x in s.policies if x.source == "personal"))
    discretionary = Decimal(sum(monthly_equivalent_paise(e.amount_paise, e.frequency) for e in s.expenses if e.bucket == "discretionary"))
    if w.spend_change_bps:
        discretionary = max(Decimal(0), discretionary * (ONE + Decimal(w.spend_change_bps) / TEN_K))
    child_cost = Decimal(0)

    liquid = Decimal(sum(x.current_value_paise for x in s.assets if x.liquidity in LIQUID))
    invested = Decimal(sum(x.current_value_paise for x in s.assets if x.liquidity in INVESTED))
    prop = Decimal(sum(x.current_value_paise for x in s.assets if x.liquidity not in LIQUID | INVESTED))
    loans = [_Loan(x.name, Decimal(x.outstanding_paise), Decimal(x.interest_rate_bps or 0) / TEN_K / 12, x.emi_paise)
             for x in s.liabilities if x.outstanding_paise > 0]
    unfunded = Decimal(0)  # spending that could not be paid from savings (shown as debt)

    # ---- scheduled outflows: existing goals + what-if goals
    outflows: List[_Outflow] = []
    for g in inp.goals:
        if g.status != "active" or g.goal_type == "retirement":
            continue
        ev = evaluate_goal(g, inp.context, a)
        if ev.months_left is None or ev.savings_target_paise is None or ev.months_left < 0 or ev.months_left > horizon:
            continue
        o = _Outflow(max(1, ev.months_left), g.name, ev.savings_target_paise)
        if ev.home_loan:
            o.home_price, o.home_loan = ev.home_loan.price_at_purchase_paise, ev.home_loan.loan_paise
        outflows.append(o)
    from app.calc.finance import inflate as calc_inflate  # local to keep top imports tidy
    for eg in w.extra_goals:
        future = calc_inflate(eg.cost_today_paise, p.inflation_bps, eg.in_months)
        if eg.goal_type == "home":
            down = future * a.home_down_payment_bps // 10000
            extra = future * a.home_extra_costs_bps // 10000
            outflows.append(_Outflow(eg.in_months, eg.name, down + extra, home_price=future, home_loan=future - down))
        else:
            outflows.append(_Outflow(eg.in_months, eg.name, future))
    child_start = None
    if w.child:
        child_start = w.child.in_months
        edu_today = w.child.education_cost_today_paise if w.child.education_cost_today_paise is not None else a.child_education_cost_paise
        edu_month = child_start + 18 * 12
        if edu_month <= horizon and edu_today:
            outflows.append(_Outflow(edu_month, "Child's education", calc_inflate(edu_today, a.education_inflation_bps, min(edu_month, 1200))))
    outflow_by_month: Dict[int, List[_Outflow]] = {}
    for o in outflows:
        outflow_by_month.setdefault(o.month, []).append(o)

    infl = Decimal(p.inflation_bps) / TEN_K
    r_cash = Decimal(p.cash_bps) / TEN_K / 12
    r_pre = Decimal(p.portfolio_bps) / TEN_K / 12
    r_post = Decimal(p.post_retirement_bps) / TEN_K / 12
    prop_growth = (ONE + infl) ** (ONE / 12)

    def net_worth() -> int:
        return to_paise(liquid + invested + prop - sum(l.balance for l in loans) - unfunded)

    def deflate(v: int, month: int) -> int:
        return to_paise(Decimal(v) / ((ONE + infl) ** (Decimal(month) / 12)))

    points: List[YearPoint] = [YearPoint(year=today.year, month=0, age=age_at(0), net_worth_paise=net_worth(), net_worth_real_paise=net_worth(),
                                         liquid_paise=to_paise(liquid), invested_paise=to_paise(invested), property_paise=to_paise(prop),
                                         debt_paise=to_paise(sum(l.balance for l in loans)), income_paise=0, spend_paise=0)]
    milestones: List[Milestone] = []
    goal_outcomes: List[GoalOutcome] = []
    year_income = year_spend = Decimal(0)
    depleted_month: Optional[int] = None
    nw_ret = nw_ret_real = savings_ret = None
    if w.career_break:
        cb = w.career_break
        milestones.append(Milestone(month=cb.start_in_months, date=add_months(today, cb.start_in_months), age=age_at(cb.start_in_months),
                                    kind="career_break", label=f"Career break for {cb.months} months"))
    if child_start is not None:
        milestones.append(Milestone(month=child_start, date=add_months(today, child_start), age=age_at(child_start), kind="child", label="A child joins the family"))
    if ret_month is not None and ret_month <= horizon:
        milestones.append(Milestone(month=ret_month, date=add_months(today, ret_month), age=age_at(ret_month), kind="retirement", label="You retire"))

    for m in range(1, horizon + 1):
        retired = ret_month is not None and m > ret_month
        if m > 1 and (m - 1) % 12 == 0:  # yearly step on each anniversary
            for inc in incomes:
                inc["amount"] *= ONE + inc["growth"]
            essential *= ONE + infl
            discretionary *= ONE + infl
            child_cost *= ONE + infl
        if child_start is not None and m == child_start + 1:
            base_cost = w.child.monthly_cost_today_paise if w.child.monthly_cost_today_paise is not None else a.child_monthly_cost_paise
            child_cost = Decimal(base_cost) * (ONE + infl) ** (Decimal(child_start) / 12)
        if child_start is not None and m == child_start + 18 * 12 + 1:
            child_cost = Decimal(0)

        on_break = w.career_break and w.career_break.start_in_months < m <= w.career_break.start_in_months + w.career_break.months
        income = sum((inc["amount"] for inc in incomes if not ((inc["stops"] and retired) or (inc["stops"] and on_break))), Decimal(0))
        spend = essential + discretionary + child_cost

        # returns on balances held through the month
        liquid += liquid * r_cash
        invested += invested * (r_post if retired else r_pre)
        prop *= prop_growth

        emi_paid = Decimal(0)
        for loan in loans:
            if loan.closed:
                continue
            interest = loan.balance * loan.rate
            if loan.emi == 0:
                loan.balance += interest  # no EMI (e.g. card): balance just accrues
                continue
            pay = min(Decimal(loan.emi), loan.balance + interest)
            loan.balance = loan.balance + interest - pay
            emi_paid += pay
            if loan.balance <= 10:
                loan.balance, loan.closed = Decimal(0), True
                milestones.append(Milestone(month=m, date=add_months(today, m), age=age_at(m), kind="loan_closed", label=f"{loan.name} paid off"))

        if w.windfall and m == w.windfall.in_months + 1:
            invested += w.windfall.amount_paise
            milestones.append(Milestone(month=m, date=add_months(today, m), age=age_at(m), kind="windfall", label="One-time money received", amount_paise=w.windfall.amount_paise))

        flow = income - spend - emi_paid
        year_income += income
        year_spend += spend + emi_paid
        if flow >= 0:
            if unfunded > 0:  # repay earlier shortfall first
                repay = min(unfunded, flow)
                unfunded -= repay
                flow -= repay
            target = (essential + child_cost + emi_paid) * a.emergency_buffer_months
            top_up = min(flow, max(Decimal(0), target - liquid)) if not retired else Decimal(0)
            liquid += top_up
            invested += flow - top_up
        else:
            need = -flow
            first, second = ("invested", "liquid") if retired else ("liquid", "invested")
            for pool in (first, second):
                have = invested if pool == "invested" else liquid
                take = min(have, need)
                if pool == "invested":
                    invested -= take
                else:
                    liquid -= take
                need -= take
            if need > 0:
                unfunded += need
                if depleted_month is None:
                    depleted_month = m
                    milestones.append(Milestone(month=m, date=add_months(today, m), age=age_at(m), kind="depleted",
                                                label="Savings run out; spending exceeds what is left"))

        for o in outflow_by_month.get(m, []):
            need = Decimal(o.amount)
            paid = Decimal(0)
            for pool in ("invested", "liquid"):
                have = invested if pool == "invested" else liquid
                take = min(have, need)
                if pool == "invested":
                    invested -= take
                else:
                    liquid -= take
                need -= take
                paid += take
            full = need <= 0
            if o.home_price:
                prop += o.home_price
                if o.home_loan:
                    loans.append(_Loan(f"{o.name} loan", Decimal(o.home_loan), Decimal(a.home_loan_rate_bps) / TEN_K / 12,
                                       calc_emi(o.home_loan, a.home_loan_rate_bps, a.home_loan_months)))
            goal_outcomes.append(GoalOutcome(name=o.name, date=add_months(today, m), cost_paise=o.amount, funded_paise=to_paise(paid), fully_funded=full))
            milestones.append(Milestone(month=m, date=add_months(today, m), age=age_at(m), kind="goal" if full else "goal_short",
                                        label=o.name if full else f"{o.name}: {to_paise(paid) * 100 // max(1, o.amount)}% funded", amount_paise=o.amount))

        if ret_month is not None and m == ret_month:
            nw_ret, nw_ret_real = net_worth(), deflate(net_worth(), m)
            savings_ret = to_paise(liquid + invested)
        if m % 12 == 0 or m == horizon:
            nw = net_worth()
            points.append(YearPoint(
                year=add_months(today, m).year, month=m, age=age_at(m), net_worth_paise=nw, net_worth_real_paise=deflate(nw, m),
                liquid_paise=to_paise(liquid), invested_paise=to_paise(invested), property_paise=to_paise(prop),
                debt_paise=to_paise(sum(l.balance for l in loans) + unfunded), income_paise=to_paise(year_income), spend_paise=to_paise(year_spend),
            ))
            year_income = year_spend = Decimal(0)

    if ret_month == 0:
        nw_ret, nw_ret_real, savings_ret = points[0].net_worth_paise, points[0].net_worth_real_paise, points[0].liquid_paise + points[0].invested_paise

    corpus = readiness = None
    ret_goal = next((g for g in inp.goals if g.goal_type == "retirement" and g.status == "active"), None)
    if ret_goal and savings_ret is not None:
        ctx = inp.context
        if p.retirement_age:
            from dataclasses import replace as dc_replace
            ctx = dc_replace(ctx, retirement_age=p.retirement_age)
        ev = evaluate_goal(ret_goal, ctx, a)
        corpus = ev.savings_target_paise
        if corpus:
            readiness = savings_ret * 10000 // corpus

    milestones.sort(key=lambda x: (x.month, x.kind))
    final = points[-1]
    summary = JourneySummary(
        months=horizon, net_worth_now_paise=points[0].net_worth_paise, retirement_month=ret_month,
        retirement_age=ret_age if ret_month is not None else None, net_worth_at_retirement_paise=nw_ret,
        net_worth_at_retirement_real_paise=nw_ret_real, savings_at_retirement_paise=savings_ret, corpus_needed_paise=corpus,
        retirement_readiness_bps=readiness, depleted_month=depleted_month, depleted_age=age_at(depleted_month) if depleted_month else None,
        money_lasts_to_age=(age_at(depleted_month) if depleted_month else age_at(horizon)),
        final_net_worth_paise=final.net_worth_paise, final_net_worth_real_paise=final.net_worth_real_paise,
        goals=goal_outcomes, goals_fully_funded=sum(g.fully_funded for g in goal_outcomes), goals_total=len(goal_outcomes),
    )
    params = {"inflation_bps": p.inflation_bps, "portfolio_return_bps": p.portfolio_bps,
              "post_retirement_return_bps": p.post_retirement_bps, "cash_return_bps": p.cash_bps,
              "salary_growth_bps": p.salary_growth_override if p.salary_growth_override is not None else max(0, a.salary_growth_bps + p.salary_growth_add)}
    return Journey(scenario=scenario, label=SCENARIO_LABELS[scenario], params=params, points=points, milestones=milestones, summary=summary)


class WhatIfComparison(BaseModel):
    base: Journey
    what_if: Journey
    lines: List[str]


def compare(base: Journey, alt: Journey) -> WhatIfComparison:
    from app.calc.normalize import inr_text

    lines: List[str] = []
    b, a = base.summary, alt.summary
    if b.net_worth_at_retirement_paise is not None and a.net_worth_at_retirement_paise is not None:
        d = a.net_worth_at_retirement_real_paise - b.net_worth_at_retirement_real_paise
        if d:
            lines.append(f"Net worth at retirement {'rises' if d > 0 else 'falls'} by {inr_text(abs(d))} in today's money.")
    if a.retirement_age != b.retirement_age and a.retirement_age:
        lines.append(f"You retire at {a.retirement_age} instead of {b.retirement_age}.")
    if a.depleted_age != b.depleted_age:
        if a.depleted_age and not b.depleted_age:
            lines.append(f"Savings would run out at age {a.depleted_age}.")
        elif b.depleted_age and not a.depleted_age:
            lines.append(f"Savings now last to age {a.money_lasts_to_age} (they ran out at {b.depleted_age}).")
        elif a.depleted_age and b.depleted_age:
            lines.append(f"Savings run out at {a.depleted_age} instead of {b.depleted_age}.")
    if a.goals_fully_funded != b.goals_fully_funded or a.goals_total != b.goals_total:
        lines.append(f"Goals fully paid for: {a.goals_fully_funded} of {a.goals_total} (was {b.goals_fully_funded} of {b.goals_total}).")
    if not lines:
        lines.append("No material change to your long-term picture.")
    return WhatIfComparison(base=base, what_if=alt, lines=lines)
