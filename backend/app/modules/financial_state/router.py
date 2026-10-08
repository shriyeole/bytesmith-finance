"""M1 HTTP API. Every query is scoped to the authenticated user."""

from datetime import date
from typing import Any, Callable, Dict, List, Optional, Type

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.models import User
from app.database import get_db
from app.modules.financial_state import models as m
from app.modules.financial_state import schemas as s
from app.modules.financial_state.enums import DEFAULT_BUCKET, DEFAULT_LIQUIDITY, AssetType, ExpenseCategory, OnboardingStep
from app.modules.financial_state.service import compute_summary, load_state, onboarding_status

router = APIRouter(tags=["Financial state"])

Hook = Callable[[Dict[str, Any], Optional[Any]], Dict[str, Any]]


def _values(payload: BaseModel, *, partial: bool) -> Dict[str, Any]:
    data = payload.model_dump(exclude_unset=partial)
    return {k: (v.value if hasattr(v, "value") else v) for k, v in data.items()}


def _crud(
    path: str,
    model: Type[Any],
    create_schema: Type[BaseModel],
    update_schema: Type[BaseModel],
    read_schema: Type[BaseModel],
    *,
    tag: str,
    required: List[str],
    hook: Optional[Hook] = None,
) -> APIRouter:
    """List / create / get / patch / delete for one user-owned table."""
    r = APIRouter(prefix=path, tags=[tag])

    def _owned(db: Session, user: User, item_id: str):
        obj = db.get(model, item_id)
        if obj is None or obj.user_id != user.id:
            raise HTTPException(status_code=404, detail=f"{tag} item not found.")
        return obj

    @r.get("", response_model=List[read_schema], name=f"list_{path.strip('/')}")
    def list_items(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
        stmt = select(model).where(model.user_id == user.id).order_by(model.created_at)
        return list(db.scalars(stmt))

    @r.post("", response_model=read_schema, status_code=201, name=f"create_{path.strip('/')}")
    def create_item(payload: create_schema, db: Session = Depends(get_db), user: User = Depends(get_current_user)):  # type: ignore[valid-type]
        values = _values(payload, partial=False)
        if hook:
            values = hook(values, None)
        obj = model(user_id=user.id, **values)
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    @r.get("/{item_id}", response_model=read_schema, name=f"get_{path.strip('/')}")
    def get_item(item_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
        return _owned(db, user, item_id)

    @r.patch("/{item_id}", response_model=read_schema, name=f"update_{path.strip('/')}")
    def update_item(item_id: str, payload: update_schema, db: Session = Depends(get_db), user: User = Depends(get_current_user)):  # type: ignore[valid-type]
        obj = _owned(db, user, item_id)
        values = _values(payload, partial=True)
        nulled = [k for k in required if k in values and values[k] is None]
        if nulled:
            raise HTTPException(status_code=422, detail=f"Fields cannot be null: {', '.join(nulled)}")
        if hook:
            values = hook(values, obj)
        for k, v in values.items():
            setattr(obj, k, v)
        db.commit()
        db.refresh(obj)
        return obj

    @r.delete("/{item_id}", status_code=204, name=f"delete_{path.strip('/')}")
    def delete_item(item_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
        db.delete(_owned(db, user, item_id))
        db.commit()
        return Response(status_code=204)

    return r


def _expense_hook(values: Dict[str, Any], existing: Optional[m.Expense]) -> Dict[str, Any]:
    """Default the bucket from the category unless the user chose one."""
    if values.get("bucket") is None and (existing is None or "category" in values):
        category = ExpenseCategory(values.get("category") or existing.category)  # type: ignore[union-attr]
        values["bucket"] = DEFAULT_BUCKET[category].value
    return values


def _asset_hook(values: Dict[str, Any], existing: Optional[m.Asset]) -> Dict[str, Any]:
    """Default liquidity from the asset type unless the user chose one."""
    if values.get("liquidity") is None and (existing is None or "asset_type" in values):
        asset_type = AssetType(values.get("asset_type") or existing.asset_type)  # type: ignore[union-attr]
        values["liquidity"] = DEFAULT_LIQUIDITY[asset_type].value
    return values


router.include_router(_crud("/household/members", m.HouseholdMember, s.MemberCreate, s.MemberUpdate, s.MemberRead,
                            tag="Household members", required=["name", "relationship", "is_dependent"]))
router.include_router(_crud("/incomes", m.IncomeStream, s.IncomeCreate, s.IncomeUpdate, s.IncomeRead,
                            tag="Income", required=["name", "kind", "owner", "amount_paise", "frequency", "is_net_of_tax", "is_active"]))
router.include_router(_crud("/expenses", m.Expense, s.ExpenseCreate, s.ExpenseUpdate, s.ExpenseRead,
                            tag="Expenses", required=["name", "category", "amount_paise", "frequency"], hook=_expense_hook))
router.include_router(_crud("/assets", m.Asset, s.AssetCreate, s.AssetUpdate, s.AssetRead,
                            tag="Assets", required=["name", "asset_type", "owner", "current_value_paise", "is_emergency_fund", "monthly_contribution_paise"], hook=_asset_hook))
router.include_router(_crud("/liabilities", m.Liability, s.LiabilityCreate, s.LiabilityUpdate, s.LiabilityRead,
                            tag="Liabilities", required=["name", "liability_type", "outstanding_paise", "emi_paise"]))
router.include_router(_crud("/insurance", m.InsurancePolicy, s.PolicyCreate, s.PolicyUpdate, s.PolicyRead,
                            tag="Insurance", required=["policy_type", "covers", "source", "cover_amount_paise", "annual_premium_paise"]))


# ---------------------------------------------------------------- household profile
@router.get("/household", response_model=s.HouseholdProfileRead, tags=["Household"])
def get_household(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    profile = db.get(m.HouseholdProfile, user.id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Household profile not created yet.")
    return profile


@router.put("/household", response_model=s.HouseholdProfileRead, tags=["Household"])
def upsert_household(payload: s.HouseholdProfileUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    values = _values(payload, partial=True)
    if values.get("tax_regime", "x") is None:
        values["tax_regime"] = "unknown"
    profile = db.get(m.HouseholdProfile, user.id)
    if profile is None:
        profile = m.HouseholdProfile(user_id=user.id)
        db.add(profile)
    for k, v in values.items():
        setattr(profile, k, v)
    # Re-check retirement age against the stored date of birth when only one side changed.
    if profile.date_of_birth and profile.retirement_age:
        age = s._age_on(profile.date_of_birth, date.today())
        if profile.retirement_age <= age:
            db.rollback()
            raise HTTPException(status_code=422, detail="retirement_age must be greater than current age.")
    db.commit()
    db.refresh(profile)
    return profile


# ---------------------------------------------------------------- summary & onboarding
@router.get("/financial-state/summary", response_model=s.FinancialSummary, tags=["Financial state"])
def get_summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return compute_summary(load_state(db, user.id))


@router.get("/onboarding", response_model=s.OnboardingStatus, tags=["Onboarding"])
def get_onboarding(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return onboarding_status(db, user.id)


@router.post("/onboarding/steps/{step}/complete", response_model=s.OnboardingStatus, tags=["Onboarding"])
def complete_step(step: OnboardingStep, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if step is OnboardingStep.PROFILE:
        raise HTTPException(status_code=422, detail="The profile step completes itself once date of birth, retirement age and employment type are saved.")
    state = db.get(m.OnboardingState, user.id)
    if state is None:
        state = m.OnboardingState(user_id=user.id, completed_steps=[])
        db.add(state)
    if step.value not in state.completed_steps:
        state.completed_steps = [*state.completed_steps, step.value]  # reassign so JSON change is tracked
    db.commit()
    return onboarding_status(db, user.id)
