"""The assistant's working copy of a user's finances, before anything is saved.

The chat model reads and rewrites this draft every turn. It is deliberately loose and in
whole rupees (how people talk), and it is never trusted: `clean()` coerces it, `progress()`
decides what is still missing, and `to_records()` turns it into the strict M1/M4 create
schemas (paise, basis points) that the normal API uses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict, ValidationError, model_validator
from typing_extensions import Annotated

from app.calc.normalize import Frequency
from app.modules.financial_state import schemas as fs
from app.modules.financial_state.enums import (
    AssetType, CoverSource, EmploymentType, ExpenseCategory, IncomeKind, IncomeStability, LiabilityType,
    MaritalStatus, Owner, PolicyType, Relationship, TaxRegime,
)
from app.modules.planning.schemas import GoalCreate, GoalType

MAX_RUPEES = 10**13  # ₹10 lakh crore; matches MAX_PAISE in M1
MAX_ITEMS = 25       # per list; a household never needs more, and it bounds prompt size


def _values(enum) -> List[str]:
    return [e.value for e in enum]


ENUMS: Dict[str, List[str]] = {
    "marital_status": _values(MaritalStatus),
    "employment_type": _values(EmploymentType),
    "income_stability": _values(IncomeStability),
    "tax_regime": _values(TaxRegime),
    "relationship": _values(Relationship),
    "income_kind": _values(IncomeKind),
    "owner": _values(Owner),
    "frequency": _values(Frequency),
    "expense_category": _values(ExpenseCategory),
    "asset_type": _values(AssetType),
    "loan_type": _values(LiabilityType),
    "policy_type": _values(PolicyType),
    "cover_source": _values(CoverSource),
    "goal_type": _values(GoalType),
}

# Sections the chat must cover, in the order it asks about them.
SECTIONS = [
    ("profile", "About you"),
    ("income", "Income"),
    ("expenses", "Monthly spending"),
    ("assets", "Savings & investments"),
    ("loans", "Loans & cards"),
    ("insurance", "Insurance"),
    ("family", "Family"),
    ("goals", "Goals"),
]
CAN_BE_NONE = {"assets", "loans", "insurance", "family", "goals"}


# ------------------------------------------------------------------ lenient field types
# A model can return 25000.4, "25,000", 1e20 or "" anywhere. One bad value must not throw
# away the whole turn, so unparseable values become None (and the chat asks again).

def _num(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, str):
        v = v.replace(",", "").replace("₹", "").strip()
        if not v:
            return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) < 1e16 else None  # drop NaN / absurd


def _lenient_int(v: Any) -> Optional[int]:
    f = _num(v)
    return None if f is None else int(round(f))


def _lenient_str(v: Any) -> Optional[str]:
    if v is None or isinstance(v, (dict, list)):
        return None
    s = str(v).strip()
    return s or None


def _lenient_date(v: Any) -> Optional[date]:
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def _lenient_bool(v: Any) -> Optional[bool]:
    if v is None or isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    return True if s in ("true", "yes", "1") else False if s in ("false", "no", "0") else None


Int = Annotated[Optional[int], BeforeValidator(_lenient_int)]
Num = Annotated[Optional[float], BeforeValidator(_num)]
Str = Annotated[Optional[str], BeforeValidator(_lenient_str)]
Day = Annotated[Optional[date], BeforeValidator(_lenient_date)]
Flag = Annotated[Optional[bool], BeforeValidator(_lenient_bool)]


class _D(BaseModel):
    model_config = ConfigDict(extra="ignore")


class ProfileDraft(_D):
    full_name: Str = None
    age: Int = None
    date_of_birth: Day = None
    city: Str = None
    marital_status: Str = None
    employment_type: Str = None
    income_stability: Str = None
    retirement_age: Int = None
    tax_regime: Str = None


class MemberDraft(_D):
    name: Str = None
    relationship: Str = None
    age: Int = None
    is_dependent: Flag = None


class IncomeDraft(_D):
    name: Str = None
    kind: Str = None
    amount: Int = None  # take-home rupees per `frequency`
    frequency: Str = None
    owner: Str = None
    yearly_raise_pct: Num = None


class ExpenseDraft(_D):
    name: Str = None
    category: Str = None
    amount: Int = None
    frequency: Str = None


class AssetDraft(_D):
    name: Str = None
    asset_type: Str = None
    value: Int = None
    monthly_investment: Int = None
    is_emergency_fund: Flag = None


class LoanDraft(_D):
    name: Str = None
    loan_type: Str = None
    outstanding: Int = None
    emi: Int = None
    interest_rate_pct: Num = None
    months_left: Int = None


class PolicyDraft(_D):
    policy_type: Str = None
    cover: Int = None
    annual_premium: Int = None
    source: Str = None
    covers: Str = None


class GoalDraft(_D):
    name: Str = None
    goal_type: Str = None
    target_year: Int = None
    cost_today: Int = None  # retirement: leave empty
    saved: Int = None
    monthly: Int = None


class Draft(_D):
    profile: ProfileDraft = ProfileDraft()
    family: List[MemberDraft] = []
    incomes: List[IncomeDraft] = []
    expenses: List[ExpenseDraft] = []
    assets: List[AssetDraft] = []
    loans: List[LoanDraft] = []
    insurance: List[PolicyDraft] = []
    goals: List[GoalDraft] = []
    none_declared: List[str] = []  # sections the user said they have nothing for

    @model_validator(mode="before")
    @classmethod
    def _shape(cls, data: Any) -> Any:
        """Drop list entries that are not objects, and a profile that is not one."""
        if not isinstance(data, dict):
            return {}
        out = dict(data)
        if not isinstance(out.get("profile"), (dict, BaseModel)):
            out.pop("profile", None)
        for key in ("family", "incomes", "expenses", "assets", "loans", "insurance", "goals"):
            rows = out.get(key)
            out[key] = [r for r in rows if isinstance(r, (dict, BaseModel))] if isinstance(rows, list) else []
        nd = out.get("none_declared")
        out["none_declared"] = [str(x) for x in nd if isinstance(x, str)] if isinstance(nd, list) else []
        return out


# ------------------------------------------------------------------ cleaning

def _enum(value: Optional[str], allowed: List[str], default: Optional[str]) -> Optional[str]:
    if value is None:
        return default
    v = str(value).strip().lower().replace(" ", "_").replace("-", "_")
    return v if v in allowed else default


def _money(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        v = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return v if 0 <= v <= MAX_RUPEES else None


def _int_in(value: Any, lo: int, hi: int) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        v = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return v if lo <= v <= hi else None


def _pct(value: Any, lo: float, hi: float) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return round(v, 2) if lo <= v <= hi else None


def _text(value: Any, limit: int = 120) -> Optional[str]:
    if value is None:
        return None
    s = " ".join(str(value).split())[:limit]
    return s or None


def clean(draft: Draft) -> Draft:
    """Coerce whatever the model returned into allowed values; drop what cannot be fixed."""
    p = draft.profile
    profile = ProfileDraft(
        full_name=_text(p.full_name),
        age=_int_in(p.age, 16, 100),
        date_of_birth=p.date_of_birth if p.date_of_birth and date(1920, 1, 1) <= p.date_of_birth <= date.today() else None,
        city=_text(p.city),
        marital_status=_enum(p.marital_status, ENUMS["marital_status"], None),
        employment_type=_enum(p.employment_type, ENUMS["employment_type"], None),
        income_stability=_enum(p.income_stability, ENUMS["income_stability"], None),
        retirement_age=_int_in(p.retirement_age, 30, 85),
        tax_regime=_enum(p.tax_regime, ENUMS["tax_regime"], None),
    )
    freq = lambda v: _enum(v, ENUMS["frequency"], "monthly")  # noqa: E731
    return Draft(
        profile=profile,
        family=[
            MemberDraft(name=_text(m.name) or (_enum(m.relationship, ENUMS["relationship"], "other") or "other").title(),
                        relationship=_enum(m.relationship, ENUMS["relationship"], "other"),
                        age=_int_in(m.age, 0, 110),
                        is_dependent=True if m.is_dependent is None else bool(m.is_dependent))
            for m in draft.family[:MAX_ITEMS]
        ],
        incomes=[
            IncomeDraft(name=_text(i.name) or "Income", kind=_enum(i.kind, ENUMS["income_kind"], "other"),
                        amount=_money(i.amount), frequency=freq(i.frequency),
                        owner=_enum(i.owner, ENUMS["owner"], "self"), yearly_raise_pct=_pct(i.yearly_raise_pct, -50, 100))
            for i in draft.incomes[:MAX_ITEMS]
        ],
        expenses=[
            ExpenseDraft(name=_text(e.name) or "Spending", category=_enum(e.category, ENUMS["expense_category"], "other"),
                         amount=_money(e.amount), frequency=freq(e.frequency))
            for e in draft.expenses[:MAX_ITEMS]
        ],
        assets=[
            AssetDraft(name=_text(a.name) or "Savings", asset_type=_enum(a.asset_type, ENUMS["asset_type"], "other"),
                       value=_money(a.value), monthly_investment=_money(a.monthly_investment) or 0,
                       is_emergency_fund=bool(a.is_emergency_fund))
            for a in draft.assets[:MAX_ITEMS]
        ],
        loans=[
            LoanDraft(name=_text(l.name) or "Loan", loan_type=_enum(l.loan_type, ENUMS["loan_type"], "other"),
                      outstanding=_money(l.outstanding), emi=_money(l.emi) or 0,
                      interest_rate_pct=_pct(l.interest_rate_pct, 0, 60), months_left=_int_in(l.months_left, 0, 600))
            for l in draft.loans[:MAX_ITEMS]
        ],
        insurance=[
            PolicyDraft(policy_type=_enum(x.policy_type, ENUMS["policy_type"], None), cover=_money(x.cover),
                        annual_premium=_money(x.annual_premium) or 0,
                        source=_enum(x.source, ENUMS["cover_source"], "personal"), covers=_text(x.covers) or "self")
            for x in draft.insurance[:MAX_ITEMS]
        ],
        goals=[
            GoalDraft(name=_text(g.name) or "Goal", goal_type=_enum(g.goal_type, ENUMS["goal_type"], "other"),
                      target_year=_int_in(g.target_year, date.today().year, date.today().year + 50),
                      cost_today=_money(g.cost_today), saved=_money(g.saved) or 0, monthly=_money(g.monthly) or 0)
            for g in draft.goals[:MAX_ITEMS]
        ],
        none_declared=sorted({s for s in draft.none_declared if s in CAN_BE_NONE}),
    )


# ------------------------------------------------------------------ progress

@dataclass
class SectionProgress:
    key: str
    label: str
    done: bool
    count: int
    missing: List[str] = field(default_factory=list)


def _age(p: ProfileDraft, today: date) -> Optional[int]:
    if p.date_of_birth:
        d = p.date_of_birth
        return today.year - d.year - ((today.month, today.day) < (d.month, d.day))
    return p.age


def progress(draft: Draft, today: Optional[date] = None) -> List[SectionProgress]:
    today = today or date.today()
    p = draft.profile
    out: List[SectionProgress] = []

    missing = []
    if _age(p, today) is None:
        missing.append("age or date of birth")
    if not p.employment_type:
        missing.append("type of work")
    if not p.retirement_age:
        missing.append("age you want to retire at")
    out.append(SectionProgress("profile", "About you", not missing, sum(v is not None for v in p.model_dump().values()), missing))

    def items(key: str, label: str, rows: list, incomplete: List[str], *, optional: bool) -> None:
        none = key in draft.none_declared and not rows
        miss = list(incomplete)
        if not rows and not none:
            miss.insert(0, "nothing yet" if optional else "at least one entry")
        out.append(SectionProgress(key, label, not miss, len(rows), miss))

    not_working = p.employment_type in ("not_working",)
    inc_missing = [f"amount for {i.name}" for i in draft.incomes if i.amount is None]
    if not draft.incomes and not_working:
        out.append(SectionProgress("income", "Income", True, 0, []))
    else:
        items("income", "Income", draft.incomes, inc_missing, optional=False)
    items("expenses", "Monthly spending", draft.expenses,
          [f"amount for {e.name}" for e in draft.expenses if e.amount is None], optional=False)
    items("assets", "Savings & investments", draft.assets,
          [f"value of {a.name}" for a in draft.assets if a.value is None], optional=True)
    items("loans", "Loans & cards", draft.loans,
          [f"amount left on {l.name}" for l in draft.loans if l.outstanding is None]
          + [f"EMI for {l.name}" for l in draft.loans if not l.emi and l.loan_type not in ("credit_card",)],
          optional=True)
    items("insurance", "Insurance", draft.insurance,
          [f"cover amount for a {x.policy_type or 'policy'}" for x in draft.insurance if x.cover is None]
          + ["type of a policy" for x in draft.insurance if x.policy_type is None], optional=True)
    items("family", "Family", draft.family, [], optional=True)
    goal_missing = []
    for g in draft.goals:
        if g.goal_type != "retirement":
            if g.target_year is None:
                goal_missing.append(f"year for {g.name}")
            if g.cost_today is None:
                goal_missing.append(f"cost of {g.name}")
    items("goals", "Goals", draft.goals, goal_missing, optional=True)
    return out


def is_complete(sections: List[SectionProgress]) -> bool:
    return all(s.done for s in sections)


# ------------------------------------------------------------------ conversion to API records

@dataclass
class Records:
    profile: fs.HouseholdProfileUpdate
    members: List[fs.MemberCreate]
    incomes: List[fs.IncomeCreate]
    expenses: List[fs.ExpenseCreate]
    assets: List[fs.AssetCreate]
    liabilities: List[fs.LiabilityCreate]
    policies: List[fs.PolicyCreate]
    goals: List[GoalCreate]
    answered: List[str]  # sections answered (with items or "none")


def _birth_from_age(age: int, today: date) -> date:
    # The 1st of this month, `age` years ago: the person is exactly `age` today.
    return date(today.year - age, today.month, 1)


def _goal_date(year: int, today: date) -> date:
    if year <= today.year:
        return date(today.year, 12, 1) if today.month < 12 else date(today.year + 1, 6, 1)
    return date(year, today.month, 1)


class DraftError(ValueError):
    def __init__(self, problems: List[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def to_records(draft: Draft, today: Optional[date] = None) -> Records:
    """Build strict create-payloads. Raises DraftError listing every problem in plain words."""
    today = today or date.today()
    problems: List[str] = []
    p = draft.profile

    def build(schema, data: Dict[str, Any], what: str):
        try:
            return schema(**{k: v for k, v in data.items() if v is not None})
        except ValidationError as exc:
            fields = ", ".join(sorted({str(e["loc"][0]) for e in exc.errors() if e.get("loc")}))
            problems.append(f"{what}: check {fields or 'the details'}")
            return None

    dob = p.date_of_birth or (_birth_from_age(p.age, today) if p.age else None)
    age = _age(p, today)
    if p.retirement_age and age is not None and p.retirement_age <= age:
        problems.append("About you: retirement age must be more than your current age")
    profile = build(fs.HouseholdProfileUpdate, {
        "full_name": p.full_name, "date_of_birth": dob, "marital_status": p.marital_status, "city": p.city,
        "retirement_age": p.retirement_age, "employment_type": p.employment_type,
        "income_stability": p.income_stability or ("stable" if p.employment_type == "salaried" else None),
        "tax_regime": p.tax_regime,
    }, "About you")

    members = [build(fs.MemberCreate, {
        "name": m.name, "relationship": m.relationship, "is_dependent": m.is_dependent,
        "date_of_birth": _birth_from_age(m.age, today) if m.age is not None else None,
    }, f"Family member {m.name}") for m in draft.family]

    incomes = [build(fs.IncomeCreate, {
        "name": i.name, "kind": i.kind, "owner": i.owner, "frequency": i.frequency,
        "amount_paise": None if i.amount is None else i.amount * 100,
        "expected_growth_bps": None if i.yearly_raise_pct is None else int(round(i.yearly_raise_pct * 100)),
    }, f"Income {i.name}") for i in draft.incomes]

    expenses = [build(fs.ExpenseCreate, {
        "name": e.name, "category": e.category, "frequency": e.frequency,
        "amount_paise": None if e.amount is None else e.amount * 100,
    }, f"Spending {e.name}") for e in draft.expenses]

    assets = [build(fs.AssetCreate, {
        "name": a.name, "asset_type": a.asset_type, "is_emergency_fund": a.is_emergency_fund,
        "current_value_paise": None if a.value is None else a.value * 100,
        "monthly_contribution_paise": (a.monthly_investment or 0) * 100,
    }, f"Savings {a.name}") for a in draft.assets]

    liabilities = [build(fs.LiabilityCreate, {
        "name": l.name, "liability_type": l.loan_type, "remaining_months": l.months_left,
        "outstanding_paise": None if l.outstanding is None else l.outstanding * 100,
        "emi_paise": (l.emi or 0) * 100,
        "interest_rate_bps": None if l.interest_rate_pct is None else int(round(l.interest_rate_pct * 100)),
    }, f"Loan {l.name}") for l in draft.loans]

    policies = [build(fs.PolicyCreate, {
        "policy_type": x.policy_type, "source": x.source, "covers": x.covers,
        "cover_amount_paise": None if x.cover is None else x.cover * 100,
        "annual_premium_paise": (x.annual_premium or 0) * 100,
    }, f"Insurance ({x.policy_type or 'policy'})") for x in draft.insurance]

    goals = []
    retirement_seen = False
    for g in draft.goals:
        if g.goal_type == "retirement":
            if retirement_seen:
                continue  # one retirement goal per person
            retirement_seen = True
            data = {"name": g.name, "goal_type": "retirement",
                    "saved_paise": (g.saved or 0) * 100, "monthly_contribution_paise": (g.monthly or 0) * 100}
        else:
            if g.target_year is None or g.cost_today is None:
                problems.append(f"Goal {g.name}: needs a year and a cost in today's money")
                continue
            data = {"name": g.name, "goal_type": g.goal_type, "target_date": _goal_date(g.target_year, today),
                    "current_cost_paise": g.cost_today * 100,
                    "saved_paise": (g.saved or 0) * 100, "monthly_contribution_paise": (g.monthly or 0) * 100}
        goals.append(build(GoalCreate, data, f"Goal {g.name}"))

    if problems:
        raise DraftError(problems)
    answered = [k for k, rows in (("income", draft.incomes), ("expenses", draft.expenses), ("assets", draft.assets),
                                  ("loans", draft.loans), ("insurance", draft.insurance))
                if rows or k in draft.none_declared]
    return Records(profile, members, incomes, expenses, assets, liabilities, policies, goals, answered)
