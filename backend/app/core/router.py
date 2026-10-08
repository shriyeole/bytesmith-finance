"""Account endpoints: who am I, and delete everything about me (spec §12.4)."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.models import User
from app.database import get_db
from app.models.goal import FinancialGoal
from app.models.profile import UserProfile

router = APIRouter(prefix="/me", tags=["Account"])


class MeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    locale: str
    created_at: datetime


@router.get("", response_model=MeRead)
def get_me(user: User = Depends(get_current_user)):
    return user


@router.delete("", status_code=204)
def delete_me(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Permanently delete the account and all financial data. M1 tables cascade from users."""
    db.execute(delete(FinancialGoal).where(FinancialGoal.user_id == user.id))
    db.execute(delete(UserProfile).where(UserProfile.id == user.id))
    db.delete(user)
    db.commit()
    return Response(status_code=204)
