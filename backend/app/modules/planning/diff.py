"""'What changed → why it matters' between two plan snapshots (spec §3.2)."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.calc.normalize import inr_text

AREAS = {
    "incomes": ("Income", "name"), "expenses": ("Spending", "name"), "assets": ("Savings & investments", "name"),
    "liabilities": ("Loans", "name"), "policies": ("Insurance", "policy_type"), "members": ("Family", "name"),
    "goals": ("Goals", "name"),
}
LABELS = {
    "amount_paise": "amount", "current_value_paise": "value", "monthly_contribution_paise": "monthly amount",
    "outstanding_paise": "amount owed", "emi_paise": "EMI", "interest_rate_bps": "interest rate", "cover_amount_paise": "cover",
    "annual_premium_paise": "premium", "saved_paise": "saved", "current_cost_paise": "cost", "target_date": "target date",
    "expected_growth_bps": "expected growth", "frequency": "frequency", "is_active": "active", "bucket": "type",
    "priority": "priority", "status": "status", "retirement_age": "retirement age", "date_of_birth": "date of birth",
    "employment_type": "work", "income_stability": "income stability", "is_emergency_fund": "emergency fund flag",
    "inflation_bps": "inflation", "expected_return_bps": "expected return", "down_payment_bps": "down payment",
}
METRICS = [  # (section, key, label, kind, which direction is better)
    ("summary", "monthly_income_paise", "Monthly income", "money", "up"),
    ("summary", "monthly_surplus_paise", "Monthly surplus", "money", "up"),
    ("summary", "net_worth_paise", "Net worth", "money", "up"),
    ("summary", "total_liabilities_paise", "Total owed", "money", "down"),
    ("emergency", "months_covered", "Emergency runway (months)", "number", "up"),
    ("goals_plan", "total_required_monthly_paise", "Monthly needed for goals", "money", "down"),
    ("goals_plan", "unfunded_monthly_paise", "Monthly goal shortfall", "money", "down"),
    ("protection.life", "gap_paise", "Life cover gap", "money", "down"),
]


def _fmt(key: str, v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if key.endswith("_paise") and isinstance(v, int):
        return inr_text(v)
    if key.endswith("_bps") and isinstance(v, int):
        return f"{v / 100:g}%"
    return str(v).replace("_", " ")


class InputChange(BaseModel):
    area: str
    kind: str  # added | removed | changed
    item: str
    text: str


class MetricChange(BaseModel):
    metric: str
    before: Optional[float] = None
    after: Optional[float] = None
    delta: Optional[float] = None
    kind: str  # money | number
    better: str  # up | down: which direction is an improvement
    improved: Optional[bool] = None


class GoalChange(BaseModel):
    goal_id: Optional[str] = None
    name: str
    before_status: Optional[str] = None
    after_status: Optional[str] = None
    before_required_paise: Optional[int] = None
    after_required_paise: Optional[int] = None


class PlanDiff(BaseModel):
    from_label: str
    to_label: str
    input_changes: List[InputChange]
    metric_changes: List[MetricChange]
    goal_changes: List[GoalChange]
    assumption_changes: List[str]
    summary: str


def _get(d: Dict[str, Any], path: str):
    for part in path.split("."):
        d = (d or {}).get(part)
    return d


def diff(before_in: Dict, before_out: Dict, after_in: Dict, after_out: Dict, from_label: str, to_label: str) -> PlanDiff:
    changes: List[InputChange] = []
    for key, (area, name_field) in AREAS.items():
        old = {r["id"]: r for r in before_in.get(key, [])}
        new = {r["id"]: r for r in after_in.get(key, [])}
        for rid in new.keys() - old.keys():
            nm = _fmt("", new[rid].get(name_field))
            changes.append(InputChange(area=area, kind="added", item=nm, text=f"Added {nm}."))
        for rid in old.keys() - new.keys():
            nm = _fmt("", old[rid].get(name_field))
            changes.append(InputChange(area=area, kind="removed", item=nm, text=f"Removed {nm}."))
        for rid in old.keys() & new.keys():
            nm = _fmt("", new[rid].get(name_field))
            for f, label in LABELS.items():
                if f in new[rid] and old[rid].get(f) != new[rid].get(f):
                    changes.append(InputChange(area=area, kind="changed", item=nm,
                                               text=f"{nm}: {label} {_fmt(f, old[rid].get(f))} → {_fmt(f, new[rid].get(f))}."))
    hb, ha = before_in.get("household") or {}, after_in.get("household") or {}
    for f in ("date_of_birth", "retirement_age", "employment_type", "income_stability"):
        if hb.get(f) != ha.get(f):
            changes.append(InputChange(area="Profile", kind="changed", item=LABELS[f],
                                       text=f"Your {LABELS[f]}: {_fmt(f, hb.get(f))} → {_fmt(f, ha.get(f))}."))
    sb, sa = before_in.get("settings") or {}, after_in.get("settings") or {}
    if sb.get("budget_rule") != sa.get("budget_rule"):
        changes.append(InputChange(area="Budget", kind="changed", item="rule",
                                   text=f"Budget rule: {_fmt('', sb.get('budget_rule'))} → {_fmt('', sa.get('budget_rule'))}."))
    if sb.get("risk_answers") != sa.get("risk_answers"):
        changes.append(InputChange(area="Risk", kind="changed", item="answers", text="Risk questionnaire answers changed."))

    assumption_changes: List[str] = []
    ab, aa = before_out.get("assumptions") or {}, after_out.get("assumptions") or {}
    for k in sorted(set(ab) | set(aa)):
        if k in ("summary", "version"):
            continue
        if ab.get(k) != aa.get(k):
            assumption_changes.append(f"{k.replace('_bps', '').replace('_', ' ').capitalize()}: {_fmt(k, ab.get(k))} → {_fmt(k, aa.get(k))}")

    metrics: List[MetricChange] = []
    for section, key, label, kind, better in METRICS:
        b, a = _get(before_out, f"{section}.{key}"), _get(after_out, f"{section}.{key}")
        if b != a:
            delta = (a - b) if isinstance(a, (int, float)) and isinstance(b, (int, float)) else None
            improved = None if delta is None else (delta > 0) == (better == "up")
            metrics.append(MetricChange(metric=label, before=b, after=a, kind=kind, delta=delta, better=better, improved=improved))

    gb = {g.get("goal_id") or g["name"]: g for g in _get(before_out, "goals_plan.goals") or []}
    ga = {g.get("goal_id") or g["name"]: g for g in _get(after_out, "goals_plan.goals") or []}
    goal_changes: List[GoalChange] = []
    for gid in list(gb.keys() | ga.keys()):
        b, a = gb.get(gid, {}), ga.get(gid, {})
        if b.get("status") != a.get("status") or b.get("required_monthly_paise") != a.get("required_monthly_paise"):
            goal_changes.append(GoalChange(goal_id=gid if gid in (a.get("goal_id"), b.get("goal_id")) else None,
                                           name=a.get("name") or b.get("name"), before_status=b.get("status"),
                                           after_status=a.get("status"), before_required_paise=b.get("required_monthly_paise"),
                                           after_required_paise=a.get("required_monthly_paise")))
    goal_changes.sort(key=lambda g: g.name)

    n = len(changes) + len(assumption_changes)
    worse = [g for g in goal_changes if g.before_status == "on_track" and g.after_status in ("at_risk", "off_track")]
    better = [g for g in goal_changes if g.after_status == "on_track" and g.before_status in ("at_risk", "off_track")]
    parts = [f"{n} change{'s' if n != 1 else ''} to your inputs" if n else "No changes to your inputs"]
    if better:
        parts.append(f"{len(better)} goal{'s' if len(better) > 1 else ''} back on track")
    if worse:
        parts.append(f"{len(worse)} goal{'s' if len(worse) > 1 else ''} slipped")
    return PlanDiff(from_label=from_label, to_label=to_label, input_changes=changes, metric_changes=metrics,
                    goal_changes=goal_changes, assumption_changes=assumption_changes, summary="; ".join(parts) + ".")
