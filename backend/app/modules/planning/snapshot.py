"""One pure path from inputs to every planning number (module M7).

capture_inputs() freezes a user's data into JSON. compute_outputs() turns that JSON into
every number the app shows. Live pages and saved plan versions both go through here, so a
saved version can always be recomputed and must match exactly (spec §12.3).
"""

from dataclasses import dataclass, field
from datetime import date
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.financial_state import models as fm
from app.modules.financial_state.schemas import FinancialSummary
from app.modules.financial_state.service import FinancialState, compute_summary
from app.modules.planning import allocation as alloc
from app.modules.planning import assumptions as asm
from app.modules.planning import budget, safety
from app.modules.planning.goals import GoalInput, PlanContext, evaluate_goal, months_between, plan_goals
from app.modules.planning.models import Goal, PlanSettings
from app.modules.planning.schemas import GoalsPlan

# Bump when any engine changes numbers for the same inputs.
MODEL_VERSION = "engines-2026.10.2"  # .2: wealth simulation + health score added

_COLLECTIONS = {
    "members": fm.HouseholdMember, "incomes": fm.IncomeStream, "expenses": fm.Expense,
    "assets": fm.Asset, "liabilities": fm.Liability, "policies": fm.InsurancePolicy, "goals": Goal,
}
_SKIP = {"user_id", "created_at", "updated_at"}
DATE_FIELDS = {"date_of_birth", "target_date", "renewal_date", "value_as_of"}


def _row(obj) -> Dict[str, Any]:
    out = {}
    for col in obj.__table__.columns:
        if col.name in _SKIP:
            continue
        v = getattr(obj, col.name)
        out[col.name] = v.isoformat() if isinstance(v, date) else v
    return out


def capture_inputs(db: Session, user_id: str, today: date) -> Dict[str, Any]:
    hp = db.get(fm.HouseholdProfile, user_id)
    ps = db.get(PlanSettings, user_id)
    data: Dict[str, Any] = {"as_of": today.isoformat(), "household": _row(hp) if hp else None}
    for key, model in _COLLECTIONS.items():
        rows = db.scalars(select(model).where(model.user_id == user_id).order_by(model.created_at, model.id))
        data[key] = [_row(r) for r in rows]
    data["settings"] = {
        "budget_rule": ps.budget_rule if ps else None,
        "custom_savings_bps": ps.custom_savings_bps if ps else None,
        "custom_wants_bps": ps.custom_wants_bps if ps else None,
        "risk_answers": ps.risk_answers if ps else None,
        "assumption_overrides": (ps.assumption_overrides or {}) if ps else {},
    }
    return data


def _ns(row: Dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(**{k: (date.fromisoformat(v) if k in DATE_FIELDS and isinstance(v, str) else v) for k, v in row.items()})


@dataclass
class Inputs:
    raw: Dict[str, Any]
    today: date
    household: Optional[SimpleNamespace]
    state: FinancialState
    goals: List[GoalInput]
    settings: Dict[str, Any]
    assumptions: asm.Assumptions
    _cache: Dict[str, Any] = field(default_factory=dict)

    # ---- cached derived pieces (each computed once per Inputs)
    def _memo(self, key, fn):
        if key not in self._cache:
            self._cache[key] = fn()
        return self._cache[key]

    @property
    def summary(self) -> FinancialSummary:
        return self._memo("summary", lambda: compute_summary(self.state))

    @property
    def context(self) -> PlanContext:
        def build():
            s = self.summary
            hp = self.household
            return PlanContext(
                today=self.today, date_of_birth=hp.date_of_birth if hp else None,
                retirement_age=hp.retirement_age if hp else None, monthly_income_paise=s.monthly_income_paise,
                monthly_spend_paise=s.monthly_essential_expenses_paise + s.monthly_discretionary_expenses_paise + s.monthly_insurance_premiums_paise,
                monthly_surplus_paise=s.monthly_surplus_paise,
            )
        return self._memo("context", build)

    @property
    def goals_plan(self) -> GoalsPlan:
        return self._memo("goals_plan", lambda: plan_goals(self.goals, self.context, self.assumptions))

    @property
    def emergency(self) -> safety.EmergencyFund:
        return self._memo("emergency", lambda: safety.emergency_fund(
            self.summary, self.household.income_stability if self.household else None, self.state.assets, self.assumptions))

    @property
    def debts(self) -> safety.DebtOverview:
        return self._memo("debts", lambda: safety.debt_overview(self.state.liabilities, self.summary, self.today, self.assumptions))

    @property
    def protection(self) -> safety.Protection:
        def build():
            edu_gap = 0
            for g in self.goals:
                if g.goal_type == "child_education" and g.status == "active":
                    ev = evaluate_goal(g, self.context, self.assumptions)
                    if ev.savings_target_paise:
                        edu_gap += max(0, ev.savings_target_paise - g.saved_paise)
            return safety.protection(self.summary, self.state.incomes, self.state.members, self.state.assets,
                                     self.state.policies, edu_gap, self.today, self.assumptions)
        return self._memo("protection", build)

    @property
    def budget(self) -> budget.BudgetComparison:
        st = self.settings
        return self._memo("budget", lambda: budget.compare_rules(
            self.summary, self.goals_plan.total_required_monthly_paise, self.emergency.monthly_to_reach_low_in_12m_paise,
            self.summary.high_cost_debt_paise, selected=st.get("budget_rule"),
            custom_savings_bps=st.get("custom_savings_bps"), custom_wants_bps=st.get("custom_wants_bps")))

    @property
    def allocation(self) -> alloc.AllocationView:
        def build():
            hp = self.household
            years_left = None
            if hp and hp.date_of_birth and hp.retirement_age:
                years_left = hp.retirement_age - (months_between(hp.date_of_birth, self.today) // 12)
            answers = self.settings.get("risk_answers")
            risk = alloc.risk_profile(answers, hp.income_stability if hp else None, self.summary.dependents_count,
                                      self.emergency.status, self.summary.high_cost_debt_paise, years_left)
            goals, weights = [], []
            if risk.answered:
                for ev in self.goals_plan.goals:
                    if ev.goal_status != "active" or ev.status in ("achieved", "needs_info") or ev.months_left is None or ev.months_left <= 0:
                        continue
                    goals.append(alloc.goal_ranges(ev.name, ev.goal_id, ev.months_left, ev.priority, risk.final_band,
                                                   (answers or {}).get("flexibility")))
                    weights.append(ev.savings_target_paise or 0)
            mix, invested, excluded = alloc.current_mix(self.state.assets, goals, weights)
            return alloc.AllocationView(risk=risk, goals=goals, current_mix=mix, invested_paise=invested,
                                        excluded_paise=excluded, disclaimer=alloc.DISCLAIMER, method=alloc.METHOD)
        return self._memo("allocation", build)


    @property
    def health(self):
        from app.modules.planning.health import health_score
        return self._memo("health", lambda: health_score(self.summary, self.emergency, self.debts, self.protection, self.goals_plan))

    def journey(self, scenario: str = "base"):
        from app.modules.planning.simulation import simulate
        return self._memo(f"journey:{scenario}", lambda: simulate(self, scenario))


def load_inputs(raw: Dict[str, Any]) -> Inputs:
    st = raw.get("settings") or {}
    goals = [
        GoalInput(goal_id=g["id"], name=g["name"], goal_type=g["goal_type"], priority=g["priority"], status=g["status"],
                  target_date=date.fromisoformat(g["target_date"]) if g.get("target_date") else None,
                  current_cost_paise=g.get("current_cost_paise"), saved_paise=g["saved_paise"],
                  monthly_contribution_paise=g["monthly_contribution_paise"], inflation_bps=g.get("inflation_bps"),
                  expected_return_bps=g.get("expected_return_bps"), down_payment_bps=g.get("down_payment_bps"))
        for g in raw.get("goals", [])
    ]
    state = FinancialState(**{k: [_ns(r) for r in raw.get(k, [])] for k in ("members", "incomes", "expenses", "assets", "liabilities", "policies")})
    return Inputs(
        raw=raw, today=date.fromisoformat(raw["as_of"]), household=_ns(raw["household"]) if raw.get("household") else None,
        state=state, goals=goals, settings=st, assumptions=asm.effective(st.get("assumption_overrides")),
    )


def compute_outputs(inp: Inputs, include_allocation: bool = True) -> Dict[str, Any]:
    out = {
        "summary": inp.summary.model_dump(mode="json"),
        "goals_plan": inp.goals_plan.model_dump(mode="json"),
        "emergency": inp.emergency.model_dump(mode="json"),
        "debts": inp.debts.model_dump(mode="json"),
        "protection": inp.protection.model_dump(mode="json"),
        "budget": inp.budget.model_dump(mode="json"),
        "assumptions": asm.as_dict(inp.assumptions),
        "health": inp.health.model_dump(mode="json"),
        "journey_summary": inp.journey("base").summary.model_dump(mode="json"),
    }
    if include_allocation:
        out["allocation"] = inp.allocation.model_dump(mode="json")
    return out
