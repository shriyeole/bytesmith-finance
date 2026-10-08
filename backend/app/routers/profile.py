"""API router for UserProfile management."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.models import User
from app.database import get_db
from app.domain.feasibility import calculate_permitted_allocation
from app.models.repository import _UNSET, get_active_goal, get_profile, upsert_profile
from app.schemas.profile import ProfileResponse, ProfileUpdateRequest

router = APIRouter(prefix="/profile", tags=["Profile (legacy baseline)"])


@router.get("", response_model=ProfileResponse)
def get_user_profile(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProfileResponse:
    """Retrieve the financial profile for the default user."""
    profile = get_profile(db, user.id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Financial profile not found.",
        )
    return ProfileResponse.from_orm_model(profile)


@router.put("", response_model=ProfileResponse)
def update_user_profile(
    payload: ProfileUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProfileResponse:
    """Create or partially update the financial profile.

    Omitted fields retain existing values; explicit null clears fields; explicit 0 stores zero.
    Enforces emergency_reserve <= existing_savings on the effective combined profile.
    Synchronizes active goal allocation without falsely clearing capping status if data becomes unknown.
    """
    existing_profile = get_profile(db, user.id)
    updates = payload.extract_paise_updates()

    # Validate effective combined profile state using persisted values for omitted fields
    new_savings = updates.get("existing_savings_paise")
    eff_savings = (
        new_savings
        if new_savings is not _UNSET
        else (existing_profile.existing_savings_paise if existing_profile else None)
    )

    new_reserve = updates.get("emergency_reserve_paise")
    eff_reserve = (
        new_reserve
        if new_reserve is not _UNSET
        else (existing_profile.emergency_reserve_paise if existing_profile else None)
    )

    if eff_savings is not None and eff_reserve is not None and eff_reserve > eff_savings:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Emergency reserve cannot exceed existing savings.",
        )

    profile = upsert_profile(session=db, user_id=user.id, **updates)

    # If an active goal exists, synchronize its permitted allocation and capping flag
    active_goal = get_active_goal(db, user.id)
    if active_goal is not None:
        permitted, is_capped, _ = calculate_permitted_allocation(
            requested_paise=active_goal.requested_allocated_savings_paise,
            existing_savings_paise=profile.existing_savings_paise,
            emergency_reserve_paise=profile.emergency_reserve_paise,
        )
        active_goal.permitted_allocated_savings_paise = permitted
        if permitted is not None:
            active_goal.is_allocation_capped = is_capped
        # When permitted is None (savings or reserve unknown), preserve existing is_allocation_capped
        # rather than falsely clearing it to False.

    db.commit()
    db.refresh(profile)
    return ProfileResponse.from_orm_model(profile)
