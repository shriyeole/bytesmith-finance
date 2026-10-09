"""Planning API (M4–M7). Every computed number goes through snapshot.Inputs, the same pure
path used to build saved plan versions, so live pages and versions can never disagree."""

from dataclasses import replace
from datetime import date, datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import Settings, get_settings
from app.core.models import User
from app.database import get_db
from app.modules.financial_state import models as fm
from app.modules.planning import allocation as alloc
from app.modules.planning import assumptions as asm
from app.modules.planning import budget as budget_engine
from app.modules.planning import alerts as alert_service
from app.modules.planning import safety
from app.modules.planning.health import HealthScore
from app.modules.planning.simulation import Journey, WhatIf, WhatIfComparison, compare, simulate
from app.modules.planning.diff import PlanDiff, diff
from app.modules.planning.goals import GoalInput, evaluate_goal, months_between, with_overrides
from app.modules.planning.models import Alert, Goal, PlanSettings, PlanVersion
from app.modules.planning.schemas import (
    DEFAULT_PRIORITY, GoalCreate, GoalEvaluation, GoalRead, GoalsPlan, GoalType, GoalUpdate, GoalWhatIf,
)
from app.modules.planning.snapshot import MODEL_VERSION, Inputs, capture_inputs, compute_outputs, load_inputs

router = APIRouter()
MAX_GOAL_MONTHS = 50 * 12


def _today() -> date:
    return date.today()


def _inputs(db: Session, user: User) -> Inputs:
    return load_inputs(capture_inputs(db, user.id, _today()))


def _settings_row(db: Session, user: User) -> PlanSettings:
    ps = db.get(PlanSettings, user.id)
    if ps is None:
        ps = PlanSettings(user_id=user.id, assumption_overrides={})
        db.add(ps)
    return ps


def _to_input(g: Goal) -> GoalInput:
    return GoalInput(
        goal_id=g.id, name=g.name, goal_type=g.goal_type, priority=g.priority, status=g.status,
        target_date=g.target_date, current_cost_paise=g.current_cost_paise, saved_paise=g.saved_paise,
        monthly_contribution_paise=g.monthly_contribution_paise, inflation_bps=g.inflation_bps,
        expected_return_bps=g.expected_return_bps, down_payment_bps=g.down_payment_bps,
    )


def _owned(db: Session, user: User, goal_id: str) -> Goal:
    g = db.get(Goal, goal_id)
    if g is None or g.user_id != user.id:
        raise HTTPException(status_code=404, detail="Goal not found.")
    return g


def _validate(values: dict, db: Session, user: User, goal_id: Optional[str] = None) -> None:
    gtype = values.get("goal_type")
    if gtype == GoalType.RETIREMENT.value:
        if values.get("target_date") is not None:
            raise HTTPException(422, "Retirement date comes from your profile's retirement age; leave target_date empty.")
        others = db.scalars(select(Goal).where(Goal.user_id == user.id, Goal.goal_type == "retirement", Goal.status != "achieved")).all()
        if any(o.id != goal_id for o in others):
            raise HTTPException(422, "You already have a retirement goal.")
    else:
        td = values.get("target_date")
        if td is None:
            raise HTTPException(422, "target_date is required for this goal.")
        if values.get("status", "active") == "active":
            months = months_between(_today(), td)
            if months < 1:
                raise HTTPException(422, "target_date must be at least a month away.")
            if months > MAX_GOAL_MONTHS:
                raise HTTPException(422, "target_date must be within 50 years.")
        if not values.get("current_cost_paise"):
            raise HTTPException(422, "current_cost_paise (cost in today's money) is required for this goal.")
    if values.get("down_payment_bps") is not None and gtype != GoalType.HOME.value:
        raise HTTPException(422, "down_payment_bps only applies to home goals.")


def _plain(payload: BaseModel, partial: bool) -> dict:
    data = payload.model_dump(exclude_unset=partial)
    return {k: (v.value if hasattr(v, "value") else v) for k, v in data.items()}


# ================================================================ features & assumptions
@router.get("/features", tags=["Planning"])
def features(settings: Settings = Depends(get_settings), user: User = Depends(get_current_user)):
    return {"allocation": settings.feature_allocation}


class AssumptionsView(BaseModel):
    effective: dict
    defaults: dict
    overrides: dict
    hash: str


def _assumptions_view(overrides: dict) -> AssumptionsView:
    a = asm.effective(overrides)
    return AssumptionsView(effective=asm.as_dict(a), defaults=asm.as_dict(asm.DEFAULT), overrides=overrides or {}, hash=asm.fingerprint(a))


@router.get("/assumptions", response_model=AssumptionsView, tags=["Assumptions"])
def get_assumptions(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ps = db.get(PlanSettings, user.id)
    return _assumptions_view(ps.assumption_overrides if ps else {})


@router.put("/assumptions", response_model=AssumptionsView, tags=["Assumptions"])
def put_assumptions(changes: Dict[str, Optional[object]], db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Partial update of overrides. A null value goes back to the default."""
    ps = _settings_row(db, user)
    merged = {**(ps.assumption_overrides or {}), **changes}
    try:
        clean = asm.validate_overrides(merged)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    ps.assumption_overrides = clean
    db.commit()
    return _assumptions_view(clean)


@router.delete("/assumptions", response_model=AssumptionsView, tags=["Assumptions"])
def reset_assumptions(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ps = _settings_row(db, user)
    ps.assumption_overrides = {}
    db.commit()
    return _assumptions_view({})


# ================================================================ goals CRUD (M4)
@router.get("/goals", response_model=List[GoalRead], tags=["Goals"])
def list_goals(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return list(db.scalars(select(Goal).where(Goal.user_id == user.id).order_by(Goal.created_at)))


@router.post("/goals", response_model=GoalRead, status_code=201, tags=["Goals"])
def create_goal(payload: GoalCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    values = _plain(payload, partial=False)
    values["priority"] = values.get("priority") or DEFAULT_PRIORITY[payload.goal_type].value
    _validate(values, db, user)
    goal = Goal(user_id=user.id, **values)
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


@router.post("/goals/preview", response_model=GoalEvaluation, tags=["Goals"])
def preview_goal(payload: GoalCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Evaluate a goal that is not saved yet (live preview in the goal editor)."""
    values = _plain(payload, partial=False)
    values["priority"] = values.get("priority") or DEFAULT_PRIORITY[payload.goal_type].value
    values.pop("notes", None)
    inp = _inputs(db, user)
    return evaluate_goal(GoalInput(**values), inp.context, inp.assumptions)


@router.get("/goals/{goal_id}", response_model=GoalRead, tags=["Goals"])
def get_goal(goal_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _owned(db, user, goal_id)


@router.patch("/goals/{goal_id}", response_model=GoalRead, tags=["Goals"])
def update_goal(goal_id: str, payload: GoalUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    goal = _owned(db, user, goal_id)
    changes = _plain(payload, partial=True)
    for required in ("name", "goal_type", "priority", "saved_paise", "monthly_contribution_paise", "status"):
        if required in changes and changes[required] is None:
            raise HTTPException(422, f"{required} cannot be null.")
    merged = {c.name: getattr(goal, c.name) for c in Goal.__table__.columns} | changes
    if merged["status"] == "active" or "target_date" in changes or "goal_type" in changes:
        _validate(merged, db, user, goal_id=goal.id)
    for k, v in changes.items():
        setattr(goal, k, v)
    db.commit()
    db.refresh(goal)
    return goal


@router.delete("/goals/{goal_id}", status_code=204, tags=["Goals"])
def delete_goal(goal_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    db.delete(_owned(db, user, goal_id))
    db.commit()
    return Response(status_code=204)


@router.get("/plan/goals", response_model=GoalsPlan, tags=["Goals"])
def goals_plan(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _inputs(db, user).goals_plan


@router.get("/goals/{goal_id}/evaluation", response_model=GoalEvaluation, tags=["Goals"])
def goal_evaluation(goal_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    goal = _owned(db, user, goal_id)
    inp = _inputs(db, user)
    return evaluate_goal(_to_input(goal), inp.context, inp.assumptions)


@router.post("/goals/{goal_id}/what-if", response_model=GoalEvaluation, tags=["Goals"])
def goal_what_if(goal_id: str, payload: GoalWhatIf, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Re-evaluate one goal with temporary changes. Nothing is saved."""
    goal = _owned(db, user, goal_id)
    inp = _inputs(db, user)
    ctx = inp.context
    overrides = payload.model_dump(exclude_none=True)
    retirement_age = overrides.pop("retirement_age", None)
    if retirement_age is not None:
        ctx = replace(ctx, retirement_age=retirement_age)
    return evaluate_goal(with_overrides(_to_input(goal), **overrides), ctx, inp.assumptions)


# ================================================================ safety (M4)
@router.get("/plan/emergency-fund", response_model=safety.EmergencyFund, tags=["Safety"])
def get_emergency_fund(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _inputs(db, user).emergency


@router.get("/plan/debts", response_model=safety.DebtOverview, tags=["Safety"])
def get_debts(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _inputs(db, user).debts


class PrepayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lump_sum_paise: int = Field(0, ge=0, le=10**15, strict=True)
    extra_monthly_paise: int = Field(0, ge=0, le=10**15, strict=True)


@router.post("/plan/debts/{liability_id}/prepay", response_model=safety.PrepayScenario, tags=["Safety"])
def prepay(liability_id: str, payload: PrepayRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    lia = db.get(fm.Liability, liability_id)
    if lia is None or lia.user_id != user.id:
        raise HTTPException(404, "Loan not found.")
    if payload.lump_sum_paise == 0 and payload.extra_monthly_paise == 0:
        raise HTTPException(422, "Enter a lump sum, an extra monthly amount, or both.")
    try:
        return safety.prepay_vs_invest(lia, payload.lump_sum_paise, payload.extra_monthly_paise, _inputs(db, user).assumptions)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.get("/plan/protection", response_model=safety.Protection, tags=["Safety"])
def get_protection(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _inputs(db, user).protection


class PlanOverview(BaseModel):
    emergency_status: str
    debt_status: str
    life_status: str
    health_status: str
    goals_counts: Dict[str, int]
    renewals_due: int
    budget_recommended: Optional[str] = None
    budget_selected: Optional[str] = None
    latest_version: Optional[int] = None


@router.get("/plan/overview", response_model=PlanOverview, tags=["Planning"])
def plan_overview(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    inp = _inputs(db, user)
    latest = db.scalar(select(func.max(PlanVersion.number)).where(PlanVersion.user_id == user.id))
    return PlanOverview(
        emergency_status=inp.emergency.status, debt_status=inp.debts.status, life_status=inp.protection.life.status,
        health_status=inp.protection.health.status, goals_counts=inp.goals_plan.counts,
        renewals_due=len(inp.protection.renewals), budget_recommended=inp.budget.recommended_id,
        budget_selected=inp.budget.selected_id, latest_version=latest,
    )


# ================================================================ budget rules (M5)
@router.get("/plan/budget", response_model=budget_engine.BudgetComparison, tags=["Budget"])
def get_budget(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _inputs(db, user).budget


class BudgetChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule: Optional[str] = None
    custom_savings_bps: Optional[int] = Field(None, ge=0, le=9000, strict=True)
    custom_wants_bps: Optional[int] = Field(None, ge=0, le=9000, strict=True)


@router.put("/plan/budget", response_model=budget_engine.BudgetComparison, tags=["Budget"])
def choose_budget(payload: BudgetChoice, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if payload.rule is not None and payload.rule not in budget_engine.RULE_IDS:
        raise HTTPException(422, f"rule must be one of: {', '.join(budget_engine.RULE_IDS)}.")
    sets = payload.model_fields_set
    ps = _settings_row(db, user)
    savings = payload.custom_savings_bps if "custom_savings_bps" in sets else ps.custom_savings_bps
    wants = payload.custom_wants_bps if "custom_wants_bps" in sets else ps.custom_wants_bps
    if savings is not None and wants is not None and savings + wants > 10000:
        raise HTTPException(422, "Savings and wants together cannot exceed 100% of income.")
    if payload.rule == "custom" and savings is None:
        raise HTTPException(422, "Set custom_savings_bps to use your own rule.")
    if "rule" in sets:
        ps.budget_rule = payload.rule
    ps.custom_savings_bps, ps.custom_wants_bps = savings, wants
    db.commit()
    return _inputs(db, user).budget


# ================================================================ risk & allocation (M6)
def _require_allocation(settings: Settings = Depends(get_settings)) -> None:
    if not settings.feature_allocation:
        raise HTTPException(404, "Not available.")


@router.get("/plan/risk-questions", response_model=List[alloc.RiskQuestion], tags=["Allocation"], dependencies=[Depends(_require_allocation)])
def risk_questions(user: User = Depends(get_current_user)):
    return alloc.questions()


@router.put("/plan/risk-answers", response_model=alloc.AllocationView, tags=["Allocation"], dependencies=[Depends(_require_allocation)])
def put_risk_answers(answers: Dict[str, str], db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        clean = alloc.validate_answers(answers)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    _settings_row(db, user).risk_answers = clean
    db.commit()
    return _inputs(db, user).allocation


@router.get("/plan/allocation", response_model=alloc.AllocationView, tags=["Allocation"], dependencies=[Depends(_require_allocation)])
def get_allocation(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _inputs(db, user).allocation


# ================================================================ plan versions (M7)
class VersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: Optional[str] = Field(None, max_length=120)


class VersionSummary(BaseModel):
    id: str
    number: int
    label: Optional[str] = None
    as_of: date
    created_at: str
    model_version: str
    assumptions_version: str
    net_worth_paise: Optional[int] = None
    monthly_surplus_paise: Optional[int] = None
    goals_on_track: Optional[int] = None
    goals_total: Optional[int] = None


class VersionDetail(VersionSummary):
    assumptions_hash: str
    inputs: dict
    outputs: dict


class VerifyResult(BaseModel):
    reproducible: bool
    model_version_matches: bool
    differences: List[str]


def _summary(v: PlanVersion) -> VersionSummary:
    o = v.outputs or {}
    gp = o.get("goals_plan") or {}
    return VersionSummary(
        id=v.id, number=v.number, label=v.label, as_of=v.as_of, created_at=v.created_at.isoformat(),
        model_version=v.model_version, assumptions_version=v.assumptions_version,
        net_worth_paise=(o.get("summary") or {}).get("net_worth_paise"),
        monthly_surplus_paise=(o.get("summary") or {}).get("monthly_surplus_paise"),
        goals_on_track=(gp.get("counts") or {}).get("on_track"), goals_total=len(gp.get("goals") or []),
    )


def _version(db: Session, user: User, version_id: str) -> PlanVersion:
    v = db.get(PlanVersion, version_id)
    if v is None or v.user_id != user.id:
        raise HTTPException(404, "Plan version not found.")
    return v


@router.post("/plan/versions", response_model=VersionSummary, status_code=201, tags=["Plan versions"])
def publish_version(payload: VersionCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    raw = capture_inputs(db, user.id, _today())
    inp = load_inputs(raw)
    number = (db.scalar(select(func.max(PlanVersion.number)).where(PlanVersion.user_id == user.id)) or 0) + 1
    v = PlanVersion(
        user_id=user.id, number=number, label=(payload.label or "").strip() or None, as_of=inp.today,
        model_version=MODEL_VERSION, assumptions_version=inp.assumptions.version,
        assumptions_hash=asm.fingerprint(inp.assumptions), inputs=raw, outputs=compute_outputs(inp),
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return _summary(v)


@router.get("/plan/versions", response_model=List[VersionSummary], tags=["Plan versions"])
def list_versions(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.scalars(select(PlanVersion).where(PlanVersion.user_id == user.id).order_by(PlanVersion.number.desc()))
    return [_summary(v) for v in rows]


@router.get("/plan/versions/{version_id}", response_model=VersionDetail, tags=["Plan versions"])
def get_version(version_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    v = _version(db, user, version_id)
    return VersionDetail(**_summary(v).model_dump(), assumptions_hash=v.assumptions_hash, inputs=v.inputs, outputs=v.outputs)


@router.get("/plan/versions/{version_id}/verify", response_model=VerifyResult, tags=["Plan versions"])
def verify_version(version_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Recompute a saved version from its stored inputs and compare with its stored outputs."""
    v = _version(db, user, version_id)
    again = compute_outputs(load_inputs(v.inputs))
    diffs = [k for k in sorted(set(again) | set(v.outputs)) if again.get(k) != v.outputs.get(k)]
    return VerifyResult(reproducible=not diffs, model_version_matches=v.model_version == MODEL_VERSION, differences=diffs)


@router.get("/plan/changes", response_model=PlanDiff, tags=["Plan versions"])
def plan_changes(from_id: Optional[str] = None, to_id: Optional[str] = None,
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """What changed between two versions. Defaults: from = latest version, to = your current data."""
    if from_id:
        fv = _version(db, user, from_id)
    else:
        fv = db.scalars(select(PlanVersion).where(PlanVersion.user_id == user.id).order_by(PlanVersion.number.desc())).first()
        if fv is None:
            raise HTTPException(404, "No saved plan version yet. Save one first.")
    if to_id:
        tv = _version(db, user, to_id)
        to_in, to_out, to_label = tv.inputs, tv.outputs, f"Version {tv.number}"
    else:
        to_in = capture_inputs(db, user.id, _today())
        to_out, to_label = compute_outputs(load_inputs(to_in)), "Now"
    return diff(fv.inputs, fv.outputs, to_in, to_out, f"Version {fv.number}", to_label)


# ================================================================ wealth journey (M8)
class JourneySet(BaseModel):
    base: Journey
    stress: Journey
    upside: Journey
    assumptions: List[str]
    notes: List[str]


@router.get("/plan/journey", response_model=JourneySet, tags=["Wealth journey"])
def get_journey(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    inp = _inputs(db, user)
    return JourneySet(
        base=inp.journey("base"), stress=inp.journey("stress"), upside=inp.journey("upside"),
        assumptions=inp.assumptions.describe(),
        notes=[
            "This is your whole household over time: every rupee of surplus is saved, goals are paid on their dates, and after retirement spending comes out of savings.",
            "Tough times = smaller raises, higher inflation, lower returns. Things go well = faster raises and better returns.",
            "Projections are estimates, not guarantees.",
        ],
    )


class SimulateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: str = Field("base", pattern="^(base|stress|upside)$")
    what_if: WhatIf


@router.post("/plan/simulate", response_model=WhatIfComparison, tags=["Wealth journey"])
def run_what_if(payload: SimulateRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Run a what-if on top of a scenario and compare it with the same scenario without it."""
    inp = _inputs(db, user)
    return compare(inp.journey(payload.scenario), simulate(inp, payload.scenario, payload.what_if))


# ================================================================ health score (M9)
@router.get("/plan/health", response_model=HealthScore, tags=["Dashboard"])
def get_health(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _inputs(db, user).health


# ================================================================ alerts & actions (M10)
class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    rule_id: str
    family: str
    severity: str
    title: str
    message: str
    action_label: Optional[str] = None
    action_link: Optional[str] = None
    impact_paise: Optional[int] = None
    status: str
    snoozed_until: Optional[date] = None
    created_at: datetime


class AlertList(BaseModel):
    alerts: List[AlertRead]
    counts: Dict[str, int]


def _sync_and_list(db: Session, user: User, include_hidden: bool) -> AlertList:
    alert_service.sync(db, user.id, _today())
    rows = alert_service.visible(db, user.id, include_hidden)
    counts: Dict[str, int] = {}
    for a in rows:
        if a.status == "open":
            counts[a.severity] = counts.get(a.severity, 0) + 1
    return AlertList(alerts=[AlertRead.model_validate(a) for a in rows], counts=counts)


@router.get("/alerts", response_model=AlertList, tags=["Alerts"])
def list_alerts(include_hidden: bool = False, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Re-checks every rule against your current data, then lists alerts (most important first)."""
    return _sync_and_list(db, user, include_hidden)


def _alert(db: Session, user: User, alert_id: str) -> Alert:
    a = db.get(Alert, alert_id)
    if a is None or a.user_id != user.id:
        raise HTTPException(404, "Alert not found.")
    return a


class SnoozeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    days: int = Field(7, ge=1, le=90, strict=True)


@router.post("/alerts/{alert_id}/dismiss", response_model=AlertRead, tags=["Alerts"])
def dismiss_alert(alert_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    a = _alert(db, user, alert_id)
    a.status, a.dismissed_severity = "dismissed", a.severity
    db.commit()
    return a


@router.post("/alerts/{alert_id}/snooze", response_model=AlertRead, tags=["Alerts"])
def snooze_alert(alert_id: str, payload: SnoozeRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from datetime import timedelta
    a = _alert(db, user, alert_id)
    a.status, a.snoozed_until = "snoozed", _today() + timedelta(days=payload.days)
    db.commit()
    return a


@router.post("/alerts/{alert_id}/done", response_model=AlertRead, tags=["Alerts"])
def act_on_alert(alert_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Record that the user acted on it (spec §3.2: log accepted actions)."""
    a = _alert(db, user, alert_id)
    a.status, a.acted_at = "acted", datetime.now(timezone.utc)
    db.commit()
    return a


@router.get("/plan/actions", response_model=List[AlertRead], tags=["Alerts"])
def top_actions(limit: int = 3, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The highest-impact things to do now: open alerts that carry an action, ranked."""
    listing = _sync_and_list(db, user, include_hidden=False)
    return [a for a in listing.alerts if a.action_link][: max(1, min(limit, 10))]
