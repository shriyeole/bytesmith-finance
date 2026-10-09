"""Financial health score (spec §9.1, module M9): 0–100, five parts of 20 points each.
Every point is explained, and each part links to the screen where it can be improved.
DRAFT methodology — to be reviewed alongside the other assumptions."""

from typing import List, Optional

from pydantic import BaseModel

from app.calc.normalize import inr_text


class ScorePart(BaseModel):
    key: str
    name: str
    points: int
    max_points: int
    detail: str
    tip: Optional[str] = None
    link: str


class HealthScore(BaseModel):
    score: int
    band: str  # excellent | good | fair | needs_work
    label: str
    parts: List[ScorePart]
    method: List[str]


def _lin(value: float, zero_at: float, full_at: float, max_pts: int = 20) -> int:
    """Linear points: 0 at zero_at, max at full_at (works for either direction)."""
    if full_at == zero_at:
        return max_pts
    frac = (value - zero_at) / (full_at - zero_at)
    return int(round(max(0.0, min(1.0, frac)) * max_pts))


def health_score(summary, emergency, debts, protection, goals_plan) -> HealthScore:
    parts: List[ScorePart] = []

    # 1. Savings rate: 0% -> 0 pts, 30%+ -> 20
    rate = summary.savings_rate_bps
    if rate is None:
        parts.append(ScorePart(key="savings", name="Saving rate", points=0, max_points=20, detail="No income recorded.", tip="Add your income.", link="/setup/income"))
    else:
        pts = _lin(rate / 100, 0, 30)
        parts.append(ScorePart(key="savings", name="Saving rate", points=pts, max_points=20,
                               detail=f"You keep {rate / 100:.0f}% of income after spending, EMIs and premiums (full marks at 30%).",
                               tip=None if pts == 20 else "Review discretionary spending on the Budget page.", link="/budget"))

    # 2. Emergency fund: share of the minimum target
    if emergency.status == "needs_info":
        parts.append(ScorePart(key="emergency", name="Emergency fund", points=0, max_points=20, detail="Add essential spending to size it.", link="/setup/expenses"))
    else:
        ratio = emergency.current_paise / emergency.target_low_paise if emergency.target_low_paise else 1
        pts = _lin(ratio, 0, 1)
        parts.append(ScorePart(key="emergency", name="Emergency fund", points=pts, max_points=20,
                               detail=f"Covers {emergency.months_covered or 0} months; minimum target is {emergency.target_months_low}.",
                               tip=None if pts == 20 else f"Set aside {inr_text(emergency.monthly_to_reach_low_in_12m_paise)} a month for a year.", link="/safety"))

    # 3. Debt: EMIs ≤20% of income full marks, ≥50% zero; high-cost debt costs 10
    dti = debts.debt_to_income_bps or 0
    pts = _lin(dti / 100, 50, 20)
    detail = f"EMIs take {dti / 100:.0f}% of take-home pay." if debts.loans else "No loans."
    if debts.high_cost_outstanding_paise:
        pts = max(0, pts - 10)
        detail += f" {inr_text(debts.high_cost_outstanding_paise)} of high-cost debt (−10)."
    parts.append(ScorePart(key="debt", name="Debt", points=pts, max_points=20, detail=detail,
                           tip=None if pts == 20 else "Clear credit-card and other high-cost debt first.", link="/safety"))

    # 4. Protection: 10 for life, 10 for health
    cover_pts = {"good": 10, "not_needed": 10, "attention": 5, "critical": 0}
    life, health = protection.life.status, protection.health.status
    pts = cover_pts.get(life, 0) + cover_pts.get(health, 0)
    parts.append(ScorePart(key="protection", name="Insurance", points=pts, max_points=20,
                           detail=f"Life cover: {life.replace('_', ' ')}. Health cover: {health.replace('_', ' ')}.",
                           tip=None if pts == 20 else "See the suggested cover on the Safety net page.", link="/safety"))

    # 5. Goals: average funded share of active, evaluable goals
    evaluable = [g for g in goals_plan.goals if g.goal_status == "active" and g.funded_bps is not None and g.status != "needs_info"]
    if not evaluable:
        parts.append(ScorePart(key="goals", name="Goals", points=10, max_points=20, detail="No goals with a date and cost yet (half marks).",
                               tip="Add retirement and your big goals.", link="/goals"))
    else:
        avg = sum(min(10000, g.funded_bps) for g in evaluable) / len(evaluable) / 10000
        pts = int(round(avg * 20))
        on = sum(1 for g in evaluable if g.status == "on_track")
        parts.append(ScorePart(key="goals", name="Goals", points=pts, max_points=20,
                               detail=f"{on} of {len(evaluable)} goals on track; on average {avg * 100:.0f}% funded by their dates.",
                               tip=None if pts == 20 else "Open a goal and try a later date or a bigger monthly amount.", link="/goals"))

    score = sum(p.points for p in parts)
    band, label = (("excellent", "Excellent") if score >= 80 else ("good", "Good") if score >= 60
                   else ("fair", "Fair") if score >= 40 else ("needs_work", "Needs work"))
    return HealthScore(score=score, band=band, label=label, parts=parts, method=[
        "Five areas, 20 points each: saving rate, emergency fund, debt, insurance and goals.",
        "Saving rate earns full marks at 30%; debt at EMIs of 20% of income or less (none at 50%).",
        "The score is a guide to where to focus, not a rating of you.",
    ])
