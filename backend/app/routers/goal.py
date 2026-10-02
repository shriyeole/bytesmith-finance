"""API router for FinancialGoal management and feasibility evaluation."""

from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.domain.feasibility import (
    InvalidTimelineError,
    calculate_calendar_months_remaining,
    calculate_permitted_allocation,
    evaluate_feasibility,
)
from app.models.repository import get_active_goal, get_profile, upsert_active_goal
from app.schemas.feasibility import GoalFeasibilityResponse
from app.schemas.goal import GoalResponse, GoalUpdateRequest

router = APIRouter(prefix="/goal", tags=["Goal"])


@router.get("", response_model=GoalResponse)
def get_current_goal(db: Session = Depends(get_db)) -> GoalResponse:
    """Retrieve the currently active financial goal for the default user."""
    goal = get_active_goal(db)
    if goal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active financial goal found.",
        )
    return GoalResponse.from_orm_model(goal)


@router.put("", response_model=GoalResponse)
def update_current_goal(
    payload: GoalUpdateRequest,
    db: Session = Depends(get_db),
) -> GoalResponse:
    """Create or update the single active financial goal.

    Requires an existing financial profile.
    Rejects past deadlines and invalid monetary inputs.
    """
    profile = get_profile(db)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Financial profile not found. Please create a profile via PUT /profile first.",
        )

    # Validate that target date is not in the past
    if payload.target_date < date.today():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Target deadline ({payload.target_date}) is in the past compared to current date ({date.today()}).",
        )

    req_paise = payload.get_requested_allocated_savings_paise()
    target_paise = payload.get_target_amount_paise()

    permitted_paise, is_capped, _ = calculate_permitted_allocation(
        requested_paise=req_paise,
        existing_savings_paise=profile.existing_savings_paise,
        emergency_reserve_paise=profile.emergency_reserve_paise,
    )

    goal = upsert_active_goal(
        session=db,
        title=payload.title,
        target_amount_paise=target_paise,
        target_date=payload.target_date,
        requested_allocated_savings_paise=req_paise,
        permitted_allocated_savings_paise=permitted_paise,
        is_allocation_capped=is_capped,
    )
    db.commit()
    db.refresh(goal)
    return GoalResponse.from_orm_model(goal)


@router.get("/feasibility", response_model=GoalFeasibilityResponse)
def get_goal_feasibility(
    current_date: Optional[date] = Query(
        default=None,
        description="Optional reference date for evaluation (defaults to today).",
    ),
    db: Session = Depends(get_db),
) -> GoalFeasibilityResponse:
    """Evaluate deterministic feasibility of the active goal against the saved profile.

    Translates domain timeline errors to HTTP 422 and missing entities to HTTP 404.
    Incomplete profile baseline inputs return INSUFFICIENT_DATA with null metrics.
    """
    profile = get_profile(db)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Financial profile not configured. Please complete PUT /profile first.",
        )

    goal = get_active_goal(db)
    if goal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active financial goal found. Please create one via PUT /goal.",
        )

    ref_date = current_date or date.today()

    try:
        result = evaluate_feasibility(
            target_amount_paise=goal.target_amount_paise,
            target_date=goal.target_date,
            requested_allocated_savings_paise=goal.requested_allocated_savings_paise,
            profile=profile,
            goal_id=goal.id,
            title=goal.title,
            current_date=ref_date,
        )
    except InvalidTimelineError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        )

    return GoalFeasibilityResponse.from_domain_result(result)
