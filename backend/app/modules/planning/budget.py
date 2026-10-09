"""Budget-rule comparison (spec §6.2-6.3, module M5).

Every rule is run on the same household. "Needs" = essential spending + insurance premiums
+ loan EMIs; "wants" = discretionary spending; "saving" = what is left for goals and safety.
A rule is judged by: does it fit your essentials, how much lifestyle change it asks for, and
how much of what your goals and safety net need it actually funds.
"""

from typing import List, Optional

from pydantic import BaseModel

from app.calc.normalize import ratio_bps
from app.modules.financial_state.schemas import FinancialSummary
from app.calc.normalize import inr_text

FIXED_RULES = [
    ("50_30_20", "50 / 30 / 20", 5000, 3000, 2000, "Simple starter: half on needs, a third on wants, a fifth saved."),
    ("50_25_25", "50 / 25 / 25", 5000, 2500, 2500, "A higher savings target with a still-generous lifestyle budget."),
    ("50_20_30", "50 / 20 / 30", 5000, 2000, 3000, "Aggressive wealth building: wants capped at a fifth of income."),
]
RULE_IDS = [r[0] for r in FIXED_RULES] + ["goal_first", "custom"]


class Split(BaseModel):
    needs_paise: int
    wants_paise: int
    savings_paise: int
    needs_bps: Optional[int] = None
    wants_bps: Optional[int] = None
    savings_bps: Optional[int] = None


class RuleResult(BaseModel):
    id: str
    name: str
    description: str
    target: Optional[Split] = None        # the rule's percentages applied to your income
    plan: Split                           # what your month looks like if you follow it
    feasible: bool                        # essentials fit inside the rule
    needs_over_paise: int                 # essentials above the rule's needs share
    wants_cut_paise: int                  # lifestyle reduction the rule asks for
    savings_increase_paise: int           # extra saving versus today
    coverage_bps: int                     # share of goals + safety needs funded (capped at 100%)
    tradeoff: str
    recommended: bool = False
    selected: bool = False


class BudgetComparison(BaseModel):
    status: str  # ok | needs_info
    income_paise: int
    current: Split
    goals_need_paise: int
    safety_need_paise: int
    total_need_paise: int
    rules: List[RuleResult]
    recommended_id: Optional[str] = None
    selected_id: Optional[str] = None
    messages: List[str]
    method: List[str]


def _split(needs: int, wants: int, savings: int, income: int) -> Split:
    return Split(needs_paise=needs, wants_paise=wants, savings_paise=savings,
                 needs_bps=ratio_bps(needs, income), wants_bps=ratio_bps(wants, income), savings_bps=ratio_bps(savings, income))


def _rupees(p: int) -> str:
    return inr_text(p)


def compare_rules(summary: FinancialSummary, goals_need: int, emergency_monthly: int, high_cost_debt: int,
                  selected: Optional[str] = None, custom_savings_bps: Optional[int] = None,
                  custom_wants_bps: Optional[int] = None) -> BudgetComparison:
    income = summary.monthly_income_paise
    needs = summary.monthly_essential_expenses_paise + summary.monthly_insurance_premiums_paise + summary.monthly_emi_paise
    wants = summary.monthly_discretionary_expenses_paise
    current_savings = income - needs - wants
    safety_need = emergency_monthly + (high_cost_debt + 11) // 12  # clear expensive debt within a year
    total_need = goals_need + safety_need
    method = [
        "Needs = essential spending + insurance premiums + loan EMIs. Wants = discretionary spending.",
        "Goals need = monthly amount all active goals require (from Goals).",
        "Safety need = building the emergency fund to its minimum within 12 months + clearing high-cost debt within 12 months.",
        "Rules are ranked by: fits your essentials, then share of needs funded, then least lifestyle change.",
    ]
    if income <= 0:
        return BudgetComparison(status="needs_info", income_paise=0, current=_split(needs, wants, 0, 0), goals_need_paise=goals_need,
                                safety_need_paise=safety_need, total_need_paise=total_need, rules=[],
                                messages=["Add your income to compare budgeting rules."], method=method)

    def coverage(savings: int) -> int:
        return 10000 if total_need <= 0 else min(10000, max(0, savings) * 10000 // total_need)

    results: List[RuleResult] = []
    for rid, name, n_bps, w_bps, s_bps, desc in FIXED_RULES:
        target = _split(income * n_bps // 10000, income * w_bps // 10000, income * s_bps // 10000, income)
        allowance = min(wants, target.wants_paise)
        savings = income - needs - allowance
        over = max(0, needs - target.needs_paise)
        cut = wants - allowance
        tradeoff = (
            f"Essentials are {ratio_bps(needs, income) / 100:.0f}% of income, above the {n_bps // 100}% this rule allows." if over
            else (f"Cut wants by {_rupees(cut)} a month." if cut else "No lifestyle change needed.")
        )
        results.append(RuleResult(
            id=rid, name=name, description=desc, target=target, plan=_split(needs, allowance, savings, income),
            feasible=over == 0, needs_over_paise=over, wants_cut_paise=cut,
            savings_increase_paise=max(0, savings - current_savings), coverage_bps=coverage(savings), tradeoff=tradeoff,
        ))

    # Goal-first: fund goals + safety first, spend what remains.
    room = income - needs - total_need
    if room >= 0:
        allowance, savings = min(wants, room), income - needs - min(wants, room)
        gf_trade = f"Wants can be up to {_rupees(room)} a month." + (f" That means cutting {_rupees(wants - allowance)}." if wants > allowance else "")
    else:
        allowance, savings = 0, max(0, income - needs)
        gf_trade = f"Even with no wants spending, you are {_rupees(-room)} a month short of what your goals need."
    results.append(RuleResult(
        id="goal_first", name="Goal-first", description="Safety and goals are funded first; lifestyle gets what is left.",
        plan=_split(needs, allowance, savings, income), feasible=room >= 0, needs_over_paise=0,
        wants_cut_paise=wants - allowance, savings_increase_paise=max(0, savings - current_savings),
        coverage_bps=coverage(savings), tradeoff=gf_trade,
    ))

    if custom_savings_bps is not None:
        w_bps = custom_wants_bps if custom_wants_bps is not None else max(0, 10000 - custom_savings_bps - (ratio_bps(needs, income) or 0))
        target = _split(income - income * (custom_savings_bps + w_bps) // 10000, income * w_bps // 10000, income * custom_savings_bps // 10000, income)
        allowance = min(wants, target.wants_paise)
        savings = income - needs - allowance
        over = max(0, needs - target.needs_paise)
        results.append(RuleResult(
            id="custom", name=f"My rule ({custom_savings_bps // 100}% saved)", description="Your own savings rate and wants cap.",
            target=target, plan=_split(needs, allowance, savings, income), feasible=over == 0, needs_over_paise=over,
            wants_cut_paise=wants - allowance, savings_increase_paise=max(0, savings - current_savings),
            coverage_bps=coverage(savings),
            tradeoff=("Essentials do not fit in the needs share left by your rule." if over else
                      (f"Cut wants by {_rupees(wants - allowance)} a month." if wants > allowance else "No lifestyle change needed.")),
        ))

    ranked = sorted(results, key=lambda r: (not r.feasible, -(r.coverage_bps // 500), r.wants_cut_paise))
    best = ranked[0]
    best.recommended = True
    for r in results:
        r.selected = r.id == selected

    messages: List[str] = []
    if needs > income:
        messages.append("Essentials, EMIs and premiums are more than your income. Fixing that comes before any rule.")
    elif not any(r.feasible for r in results):
        messages.append("Your essentials are above every rule's needs share; the goal-first view shows the real trade-off.")
    if best.coverage_bps < 10000:
        msg = f"{best.name} funds {best.coverage_bps / 100:.0f}% of what your goals and safety net need."
        gf = next(r for r in results if r.id == "goal_first")
        if gf is not best and gf.coverage_bps > best.coverage_bps:
            msg += f" Goal-first reaches {gf.coverage_bps / 100:.0f}%, but only by cutting {_rupees(gf.wants_cut_paise)} of wants a month."
        messages.append(msg + " Consider later dates or smaller targets for lower-priority goals.")

    return BudgetComparison(
        status="ok", income_paise=income, current=_split(needs, wants, current_savings, income), goals_need_paise=goals_need,
        safety_need_paise=safety_need, total_need_paise=total_need, rules=results, recommended_id=best.id,
        selected_id=selected if selected in RULE_IDS else None, messages=messages, method=method,
    )
