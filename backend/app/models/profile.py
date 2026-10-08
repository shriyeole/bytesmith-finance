"""UserProfile SQLAlchemy ORM model for ByteSmiths Finance Copilot."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import BigInteger, CheckConstraint, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.goal import FinancialGoal

DEFAULT_USER_ID = "user_default"


class UserProfile(Base):
    """Stores the single-user financial profile and baseline commitments.

    All monetary figures are stored strictly as integer paise.
    Nullable fields represent incomplete/omitted baseline estimates (never defaulted to zero).
    """

    __tablename__ = "user_profiles"

    id: Mapped[str] = mapped_column(
        String(128), primary_key=True, default=DEFAULT_USER_ID
    )
    # All financial profile fields are nullable until entered by the user
    monthly_take_home_income_paise: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True, default=None
    )
    existing_savings_paise: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True, default=None
    )
    emergency_reserve_paise: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True, default=None
    )
    monthly_fixed_commitments_paise: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True, default=None
    )
    monthly_estimated_living_expenses_paise: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True, default=None
    )
    monthly_estimated_discretionary_paise: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True, default=None
    )
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="INR"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    goals: Mapped[List["FinancialGoal"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "(emergency_reserve_paise IS NULL OR existing_savings_paise IS NULL) "
            "OR (emergency_reserve_paise <= existing_savings_paise)",
            name="ck_emergency_reserve_le_savings",
        ),
        CheckConstraint(
            "monthly_take_home_income_paise IS NULL OR monthly_take_home_income_paise >= 0",
            name="ck_income_non_negative",
        ),
        CheckConstraint(
            "existing_savings_paise IS NULL OR existing_savings_paise >= 0",
            name="ck_savings_non_negative",
        ),
        CheckConstraint(
            "emergency_reserve_paise IS NULL OR emergency_reserve_paise >= 0",
            name="ck_reserve_non_negative",
        ),
        CheckConstraint(
            "monthly_fixed_commitments_paise IS NULL OR monthly_fixed_commitments_paise >= 0",
            name="ck_fixed_non_negative",
        ),
        CheckConstraint(
            "monthly_estimated_living_expenses_paise IS NULL OR monthly_estimated_living_expenses_paise >= 0",
            name="ck_living_non_negative",
        ),
        CheckConstraint(
            "monthly_estimated_discretionary_paise IS NULL OR monthly_estimated_discretionary_paise >= 0",
            name="ck_disc_non_negative",
        ),
    )

    @property
    def unencumbered_savings_paise(self) -> int:
        """Calculate liquid savings strictly above protected emergency reserve.

        LIMITATION & SAFETY NOTE:
        This property computes a raw mathematical floor on the persistence model.
        When a profile is incomplete (is_complete == False, e.g. savings or reserve
        are not yet entered), this return value (0) must NOT be mistaken for verified,
        goal-allocatable savings. The domain goal engine and API layers must verify
        profile completeness before allocating savings to goals.
        """
        if self.existing_savings_paise is None:
            return 0
        reserve = self.emergency_reserve_paise if self.emergency_reserve_paise is not None else 0
        return max(0, self.existing_savings_paise - reserve)

    @property
    def is_complete(self) -> bool:
        """Check whether the profile contains all required monetary baseline inputs.

        Rule:
        - Monthly take-home income must be present and > 0.
        - Existing savings, emergency reserve, fixed commitments, living expenses,
          and discretionary expenses must all be present and >= 0.
        """
        if self.monthly_take_home_income_paise is None or self.monthly_take_home_income_paise <= 0:
            return False
        if self.existing_savings_paise is None or self.existing_savings_paise < 0:
            return False
        if self.emergency_reserve_paise is None or self.emergency_reserve_paise < 0:
            return False
        if self.monthly_fixed_commitments_paise is None or self.monthly_fixed_commitments_paise < 0:
            return False
        if (
            self.monthly_estimated_living_expenses_paise is None
            or self.monthly_estimated_living_expenses_paise < 0
        ):
            return False
        if (
            self.monthly_estimated_discretionary_paise is None
            or self.monthly_estimated_discretionary_paise < 0
        ):
            return False
        if self.emergency_reserve_paise > self.existing_savings_paise:
            return False
        return True
