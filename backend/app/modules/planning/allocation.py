"""Risk profile and goal-level asset-class ranges (spec §4.7, §7, module M6).

EDUCATIONAL FRAMEWORK, NOT ADVICE. Ranges are product-design defaults that need review by a
qualified finance reviewer and counsel before launch (spec §7.3, §13). No securities or
products are named. The feature is behind FEATURE_ALLOCATION.
"""

from typing import Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel

CLASSES = ("equity", "fixed_income", "gold", "cash")
BAND_NAMES = {1: "Conservative", 2: "Moderately conservative", 3: "Balanced", 4: "Growth", 5: "Aggressive"}
EQUITY_CAP_BY_BAND = {1: 25, 2: 40, 3: 60, 4: 75, 5: 85}

QUESTIONS = [
    {"id": "market_drop", "text": "If your investments fell 20% in a year, what would you most likely do?",
     "options": [("sell_all", "Sell everything to stop the loss", 1), ("sell_some", "Sell some of it", 2),
                 ("hold", "Hold and wait", 3), ("buy_more", "Invest more while prices are low", 4)]},
    {"id": "priority", "text": "Which matters more to you?",
     "options": [("safety", "Not losing money", 1), ("mostly_safety", "Mostly safety, a little growth", 2),
                 ("balance", "A balance of both", 3), ("growth", "Growth, accepting bigger swings", 4)]},
    {"id": "experience", "text": "What have you invested in before?",
     "options": [("none", "Nothing yet", 1), ("deposits", "Only FDs / PPF / savings", 2),
                 ("funds", "Mutual funds", 3), ("stocks", "Stocks directly", 4)]},
    {"id": "flexibility", "text": "If a goal falls short, could you delay it?",
     "options": [("no", "No, the date is fixed", 1), ("months", "By a few months", 2),
                 ("year", "By a year or two", 3), ("yes", "Yes, the date is flexible", 4)]},
]
_SCORES = {q["id"]: {o[0]: o[2] for o in q["options"]} for q in QUESTIONS}

# Horizon band -> class -> (min %, max %). Illustrative, from spec §7.3.
HORIZON_BANDS: List[Tuple[str, str, int, Dict[str, Tuple[int, int]]]] = [
    ("short", "Under 2 years", 24, {"equity": (0, 10), "fixed_income": (50, 80), "gold": (0, 5), "cash": (15, 40)}),
    ("medium", "2–7 years", 84, {"equity": (20, 40), "fixed_income": (45, 70), "gold": (5, 10), "cash": (0, 10)}),
    ("long", "7–15 years", 180, {"equity": (40, 60), "fixed_income": (30, 50), "gold": (5, 10), "cash": (0, 5)}),
    ("very_long", "Over 15 years", 10**6, {"equity": (60, 80), "fixed_income": (15, 30), "gold": (5, 10), "cash": (0, 5)}),
]

ASSET_CLASS = {
    "mutual_fund": "equity", "direct_equity": "equity",
    "fixed_deposit": "fixed_income", "epf": "fixed_income", "ppf": "fixed_income", "nps": "fixed_income",
    "gold": "gold", "cash": "cash", "savings_account": "cash",
}

DISCLAIMER = ("General asset-class guidance for education, not investment advice or a recommendation of any "
              "product. Ranges are illustrative and based on assumptions. Consider a SEBI-registered investment "
              "adviser for personalised advice.")


class RiskQuestion(BaseModel):
    id: str
    text: str
    options: List[Dict[str, str]]


class RiskProfile(BaseModel):
    answered: bool
    willingness_band: Optional[int] = None
    capacity_band: int
    final_band: Optional[int] = None
    final_name: Optional[str] = None
    equity_cap_pct: Optional[int] = None
    capacity_reasons: List[str]
    limiting_factor: Optional[str] = None  # "capacity" | "willingness" | "both"


class ClassRange(BaseModel):
    asset_class: str
    min_pct: int
    max_pct: int


class GoalAllocation(BaseModel):
    goal_id: Optional[str]
    name: str
    horizon_band: str
    horizon_label: str
    months_left: int
    ranges: List[ClassRange]
    notes: List[str]


class MixCompare(BaseModel):
    asset_class: str
    current_pct: Optional[float] = None
    target_min_pct: Optional[float] = None
    target_max_pct: Optional[float] = None
    position: Optional[str] = None  # below | within | above


class AllocationView(BaseModel):
    risk: RiskProfile
    goals: List[GoalAllocation]
    current_mix: List[MixCompare]
    invested_paise: int
    excluded_paise: int
    disclaimer: str
    method: List[str]


def questions() -> List[RiskQuestion]:
    return [RiskQuestion(id=q["id"], text=q["text"], options=[{"value": o[0], "label": o[1]} for o in q["options"]]) for q in QUESTIONS]


def validate_answers(answers: dict) -> dict:
    clean = {}
    for qid, options in _SCORES.items():
        v = answers.get(qid)
        if v not in options:
            raise ValueError(f"Answer '{qid}' must be one of: {', '.join(options)}.")
        clean[qid] = v
    extra = set(answers) - set(_SCORES)
    if extra:
        raise ValueError(f"Unknown questions: {', '.join(sorted(extra))}.")
    return clean


def _willingness(answers: dict) -> int:
    avg = sum(_SCORES[q][answers[q]] for q in ("market_drop", "priority", "experience")) / 3
    for limit, band in ((1.5, 1), (2.2, 2), (2.9, 3), (3.5, 4)):
        if avg <= limit:
            return band
    return 5


def risk_profile(answers: Optional[dict], income_stability: Optional[str], dependents: int, emergency_status: str,
                 high_cost_debt_paise: int, years_to_retirement: Optional[int]) -> RiskProfile:
    capacity, reasons = 5, []
    if income_stability == "uncertain":
        capacity -= 2
        reasons.append("Irregular income lowers how much loss you can absorb.")
    elif income_stability == "variable":
        capacity -= 1
        reasons.append("Variable income lowers how much loss you can absorb.")
    if dependents >= 2:
        capacity -= 1
        reasons.append("Several people depend on your income.")
    if emergency_status not in ("good",):
        capacity -= 1
        reasons.append("Your emergency fund is below target.")
    if high_cost_debt_paise > 0:
        capacity -= 1
        reasons.append("You carry high-cost debt.")
    if years_to_retirement is not None and years_to_retirement < 10:
        capacity -= 1
        reasons.append("Retirement is less than 10 years away.")
    capacity = max(1, capacity)
    if not reasons:
        reasons.append("Stable income, a full emergency fund and no expensive debt give you room to take risk.")

    if not answers:
        return RiskProfile(answered=False, capacity_band=capacity, capacity_reasons=reasons)
    willing = _willingness(answers)
    final = min(capacity, willing)
    limiting = "both" if capacity == willing else ("capacity" if capacity < willing else "willingness")
    return RiskProfile(answered=True, willingness_band=willing, capacity_band=capacity, final_band=final,
                       final_name=BAND_NAMES[final], equity_cap_pct=EQUITY_CAP_BY_BAND[final],
                       capacity_reasons=reasons, limiting_factor=limiting)


def goal_ranges(name: str, goal_id: Optional[str], months_left: int, priority: str, band: int,
                flexibility: Optional[str]) -> GoalAllocation:
    key, label, _, base = next(b for b in HORIZON_BANDS if months_left <= b[2])
    ranges = dict(base)
    notes: List[str] = []
    cap = EQUITY_CAP_BY_BAND[band]
    if priority == "essential" and flexibility == "no":
        cap = max(0, cap - 10)
        notes.append("Lower equity ceiling: this is an essential goal and you said its date cannot move.")
    eq_lo, eq_hi = ranges["equity"]
    if eq_hi > cap:
        moved = eq_hi - cap
        eq_hi, eq_lo = cap, min(eq_lo, cap)
        fi_lo, fi_hi = ranges["fixed_income"]
        ranges["fixed_income"] = (fi_lo, min(100, fi_hi + moved))
        notes.append(f"Equity capped at {cap}% by your risk profile.")
    ranges["equity"] = (eq_lo, eq_hi)
    if key == "short":
        notes.append("Money needed within 2 years should mostly stay out of the stock market.")
    return GoalAllocation(goal_id=goal_id, name=name, horizon_band=key, horizon_label=label, months_left=months_left,
                          ranges=[ClassRange(asset_class=c, min_pct=ranges[c][0], max_pct=ranges[c][1]) for c in CLASSES], notes=notes)


def current_mix(assets: Sequence, goals: List[GoalAllocation], weights: List[int]) -> Tuple[List[MixCompare], int, int]:
    totals = {c: 0 for c in CLASSES}
    excluded = 0
    for a in assets:
        cls = ASSET_CLASS.get(a.asset_type)
        if cls:
            totals[cls] += a.current_value_paise
        else:
            excluded += a.current_value_paise
    invested = sum(totals.values())
    weight_sum = sum(weights)
    out = []
    for c in CLASSES:
        lo = hi = None
        if goals and weight_sum > 0:
            lo = round(sum(next(r.min_pct for r in g.ranges if r.asset_class == c) * w for g, w in zip(goals, weights)) / weight_sum, 1)
            hi = round(sum(next(r.max_pct for r in g.ranges if r.asset_class == c) * w for g, w in zip(goals, weights)) / weight_sum, 1)
        cur = round(totals[c] * 100 / invested, 1) if invested else None
        pos = None
        if cur is not None and lo is not None:
            pos = "below" if cur < lo else ("above" if cur > hi else "within")
        out.append(MixCompare(asset_class=c, current_pct=cur, target_min_pct=lo, target_max_pct=hi, position=pos))
    return out, invested, excluded


METHOD = [
    "Risk capacity comes from your data (income stability, dependents, emergency fund, debt, years to retirement).",
    "Risk willingness comes from your answers. The lower of the two sets your profile: the strictest constraint wins.",
    "Each goal gets ranges by how far away it is; nearer goals hold less equity regardless of your age.",
    "The overall target weights each goal by the amount it needs. Property and business assets are left out of the mix.",
    "Mutual funds are counted as equity and NPS as fixed income for simplicity.",
]
