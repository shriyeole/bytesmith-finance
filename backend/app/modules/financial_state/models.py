"""M1 ORM models. Money = BigInteger paise; rates = integer basis points (800 = 8.00%)."""

import uuid
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import JSON, BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from app.core.models import utcnow
from app.database import Base


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


class _Owned:
    """Columns shared by every user-owned row."""

    @declared_attr
    def user_id(cls) -> Mapped[str]:
        return mapped_column(String(128), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class HouseholdProfile(Base):
    """One per user: stable context for planning (spec §4.1)."""

    __tablename__ = "household_profiles"

    user_id: Mapped[str] = mapped_column(String(128), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(120))
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date)
    marital_status: Mapped[Optional[str]] = mapped_column(String(32))
    city: Mapped[Optional[str]] = mapped_column(String(80))
    retirement_age: Mapped[Optional[int]] = mapped_column(Integer)
    employment_type: Mapped[Optional[str]] = mapped_column(String(32))
    income_stability: Mapped[Optional[str]] = mapped_column(String(32))
    tax_regime: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        CheckConstraint("retirement_age IS NULL OR (retirement_age BETWEEN 30 AND 85)", name="ck_hp_retirement_age"),
    )


class OnboardingState(Base):
    """Steps the user explicitly finished (lets "I have no loans" count as done)."""

    __tablename__ = "onboarding_states"

    user_id: Mapped[str] = mapped_column(String(128), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    completed_steps: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class HouseholdMember(_Owned, Base):
    __tablename__ = "household_members"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: _new_id("mem"))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    relationship: Mapped[str] = mapped_column(String(32), nullable=False)
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date)
    is_dependent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class IncomeStream(_Owned, Base):
    __tablename__ = "income_streams"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: _new_id("inc"))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    owner: Mapped[str] = mapped_column(String(16), nullable=False, default="self")
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    frequency: Mapped[str] = mapped_column(String(16), nullable=False, default="monthly")
    is_net_of_tax: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    expected_growth_bps: Mapped[Optional[int]] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        CheckConstraint("amount_paise >= 0", name="ck_inc_amount"),
        CheckConstraint("expected_growth_bps IS NULL OR expected_growth_bps BETWEEN -5000 AND 10000", name="ck_inc_growth"),
    )


class Expense(_Owned, Base):
    __tablename__ = "expenses"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: _new_id("exp"))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    bucket: Mapped[str] = mapped_column(String(16), nullable=False)
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    frequency: Mapped[str] = mapped_column(String(16), nullable=False, default="monthly")
    inflation_bps: Mapped[Optional[int]] = mapped_column(Integer)

    __table_args__ = (
        CheckConstraint("amount_paise >= 0", name="ck_exp_amount"),
        CheckConstraint("inflation_bps IS NULL OR inflation_bps BETWEEN 0 AND 5000", name="ck_exp_inflation"),
    )


class Asset(_Owned, Base):
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: _new_id("ast"))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False)
    owner: Mapped[str] = mapped_column(String(16), nullable=False, default="self")
    current_value_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    liquidity: Mapped[str] = mapped_column(String(16), nullable=False)
    is_emergency_fund: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    monthly_contribution_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    value_as_of: Mapped[Optional[date]] = mapped_column(Date)

    __table_args__ = (
        CheckConstraint("current_value_paise >= 0", name="ck_ast_value"),
        CheckConstraint("monthly_contribution_paise >= 0", name="ck_ast_contribution"),
    )


class Liability(_Owned, Base):
    __tablename__ = "liabilities"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: _new_id("lia"))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    liability_type: Mapped[str] = mapped_column(String(32), nullable=False)
    lender: Mapped[Optional[str]] = mapped_column(String(120))
    outstanding_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    interest_rate_bps: Mapped[Optional[int]] = mapped_column(Integer)
    emi_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    remaining_months: Mapped[Optional[int]] = mapped_column(Integer)

    __table_args__ = (
        CheckConstraint("outstanding_paise >= 0", name="ck_lia_outstanding"),
        CheckConstraint("emi_paise >= 0", name="ck_lia_emi"),
        CheckConstraint("interest_rate_bps IS NULL OR interest_rate_bps BETWEEN 0 AND 6000", name="ck_lia_rate"),
        CheckConstraint("remaining_months IS NULL OR remaining_months BETWEEN 0 AND 600", name="ck_lia_months"),
    )


class InsurancePolicy(_Owned, Base):
    __tablename__ = "insurance_policies"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: _new_id("pol"))
    policy_type: Mapped[str] = mapped_column(String(32), nullable=False)
    provider: Mapped[Optional[str]] = mapped_column(String(120))
    covers: Mapped[str] = mapped_column(String(120), nullable=False, default="self")
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="personal")
    cover_amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    annual_premium_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    renewal_date: Mapped[Optional[date]] = mapped_column(Date)

    __table_args__ = (
        CheckConstraint("cover_amount_paise >= 0", name="ck_pol_cover"),
        CheckConstraint("annual_premium_paise >= 0", name="ck_pol_premium"),
    )
