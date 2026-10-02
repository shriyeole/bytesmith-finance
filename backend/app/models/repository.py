"""Persistence helper operations for single-user profile and active goal."""

from datetime import date
from typing import Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.goal import FinancialGoal
from app.models.profile import DEFAULT_USER_ID, UserProfile


def get_profile(session: Session, user_id: str = DEFAULT_USER_ID) -> Optional[UserProfile]:
    """Retrieve the financial profile for the specified user."""
    return session.get(UserProfile, user_id)


_UNSET = object()


def upsert_profile(
    session: Session,
    monthly_take_home_income_paise: Optional[int] = _UNSET,  # type: ignore[assignment]
    existing_savings_paise: Optional[int] = _UNSET,  # type: ignore[assignment]
    emergency_reserve_paise: Optional[int] = _UNSET,  # type: ignore[assignment]
    monthly_fixed_commitments_paise: Optional[int] = _UNSET,  # type: ignore[assignment]
    monthly_estimated_living_expenses_paise: Optional[int] = _UNSET,  # type: ignore[assignment]
    monthly_estimated_discretionary_paise: Optional[int] = _UNSET,  # type: ignore[assignment]
    currency: str = _UNSET,  # type: ignore[assignment]
    user_id: str = DEFAULT_USER_ID,
) -> UserProfile:
    """Create or update the single-user financial profile.

    Allows any monetary fields to remain unset (None).
    On update, only explicitly provided fields are modified.
    """
    profile = get_profile(session, user_id)
    if profile is None:
        profile = UserProfile(
            id=user_id,
            monthly_take_home_income_paise=(
                monthly_take_home_income_paise if monthly_take_home_income_paise is not _UNSET else None
            ),
            existing_savings_paise=(
                existing_savings_paise if existing_savings_paise is not _UNSET else None
            ),
            emergency_reserve_paise=(
                emergency_reserve_paise if emergency_reserve_paise is not _UNSET else None
            ),
            monthly_fixed_commitments_paise=(
                monthly_fixed_commitments_paise if monthly_fixed_commitments_paise is not _UNSET else None
            ),
            monthly_estimated_living_expenses_paise=(
                monthly_estimated_living_expenses_paise
                if monthly_estimated_living_expenses_paise is not _UNSET
                else None
            ),
            monthly_estimated_discretionary_paise=(
                monthly_estimated_discretionary_paise
                if monthly_estimated_discretionary_paise is not _UNSET
                else None
            ),
            currency=currency if currency is not _UNSET else "INR",
        )
        session.add(profile)
    else:
        if monthly_take_home_income_paise is not _UNSET:
            profile.monthly_take_home_income_paise = monthly_take_home_income_paise
        if existing_savings_paise is not _UNSET:
            profile.existing_savings_paise = existing_savings_paise
        if emergency_reserve_paise is not _UNSET:
            profile.emergency_reserve_paise = emergency_reserve_paise
        if monthly_fixed_commitments_paise is not _UNSET:
            profile.monthly_fixed_commitments_paise = monthly_fixed_commitments_paise
        if monthly_estimated_living_expenses_paise is not _UNSET:
            profile.monthly_estimated_living_expenses_paise = monthly_estimated_living_expenses_paise
        if monthly_estimated_discretionary_paise is not _UNSET:
            profile.monthly_estimated_discretionary_paise = monthly_estimated_discretionary_paise
        if currency is not _UNSET:
            profile.currency = currency

    session.flush()
    return profile


def get_active_goal(session: Session, user_id: str = DEFAULT_USER_ID) -> Optional[FinancialGoal]:
    """Retrieve the currently active financial goal for the user."""
    stmt = (
        select(FinancialGoal)
        .where(FinancialGoal.user_id == user_id, FinancialGoal.status == "ACTIVE")
    )
    return session.scalars(stmt).first()


def upsert_active_goal(
    session: Session,
    title: str,
    target_amount_paise: int,
    target_date: date,
    requested_allocated_savings_paise: int = 0,
    permitted_allocated_savings_paise: int = 0,
    is_allocation_capped: bool = False,
    user_id: str = DEFAULT_USER_ID,
) -> FinancialGoal:
    """Maintain at most one active goal for the user by updating existing or creating new."""
    active_goal = get_active_goal(session, user_id)
    if active_goal is None:
        active_goal = FinancialGoal(
            user_id=user_id,
            title=title,
            target_amount_paise=target_amount_paise,
            target_date=target_date,
            requested_allocated_savings_paise=requested_allocated_savings_paise,
            permitted_allocated_savings_paise=permitted_allocated_savings_paise,
            is_allocation_capped=is_allocation_capped,
            status="ACTIVE",
        )
        session.add(active_goal)
    else:
        active_goal.title = title
        active_goal.target_amount_paise = target_amount_paise
        active_goal.target_date = target_date
        active_goal.requested_allocated_savings_paise = requested_allocated_savings_paise
        active_goal.permitted_allocated_savings_paise = permitted_allocated_savings_paise
        active_goal.is_allocation_capped = is_allocation_capped

    session.flush()
    return active_goal
