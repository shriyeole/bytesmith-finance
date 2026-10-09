"""M4 tables. Money = BigInteger paise; rates = basis points."""

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import JSON, BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import utcnow
from app.database import Base


class Goal(Base):
    """A future objective. For non-retirement goals `current_cost_paise` is the price in
    today's money; for retirement it is the monthly spend in today's money (null = use
    current spending) and the date comes from the household profile."""

    __tablename__ = "goals"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: f"gol_{uuid.uuid4().hex[:16]}")
    user_id: Mapped[str] = mapped_column(String(128), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    goal_type: Mapped[str] = mapped_column(String(32), nullable=False)
    priority: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    target_date: Mapped[Optional[date]] = mapped_column(Date)
    current_cost_paise: Mapped[Optional[int]] = mapped_column(BigInteger)
    saved_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    monthly_contribution_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    inflation_bps: Mapped[Optional[int]] = mapped_column(Integer)
    expected_return_bps: Mapped[Optional[int]] = mapped_column(Integer)
    down_payment_bps: Mapped[Optional[int]] = mapped_column(Integer)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        CheckConstraint("current_cost_paise IS NULL OR current_cost_paise >= 0", name="ck_goal_cost"),
        CheckConstraint("saved_paise >= 0", name="ck_goal_saved"),
        CheckConstraint("monthly_contribution_paise >= 0", name="ck_goal_monthly"),
        CheckConstraint("inflation_bps IS NULL OR inflation_bps BETWEEN 0 AND 3000", name="ck_goal_inflation"),
        CheckConstraint("expected_return_bps IS NULL OR expected_return_bps BETWEEN 0 AND 3000", name="ck_goal_return"),
        CheckConstraint("down_payment_bps IS NULL OR down_payment_bps BETWEEN 0 AND 10000", name="ck_goal_down_payment"),
    )


class PlanSettings(Base):
    """Per-user planning choices: chosen budget rule, risk answers, assumption overrides."""

    __tablename__ = "plan_settings"

    user_id: Mapped[str] = mapped_column(String(128), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    budget_rule: Mapped[Optional[str]] = mapped_column(String(32))
    custom_savings_bps: Mapped[Optional[int]] = mapped_column(Integer)
    custom_wants_bps: Mapped[Optional[int]] = mapped_column(Integer)
    risk_answers: Mapped[Optional[dict]] = mapped_column(JSON)
    assumption_overrides: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class PlanVersion(Base):
    """An immutable, reproducible snapshot of a user's plan (spec §12.3).
    Never updated after insert: `inputs` + `model_version` reproduce `outputs` exactly."""

    __tablename__ = "plan_versions"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: f"ver_{uuid.uuid4().hex[:16]}")
    user_id: Mapped[str] = mapped_column(String(128), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[Optional[str]] = mapped_column(String(120))
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    model_version: Mapped[str] = mapped_column(String(40), nullable=False)
    assumptions_version: Mapped[str] = mapped_column(String(40), nullable=False)
    assumptions_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    inputs: Mapped[dict] = mapped_column(JSON, nullable=False)
    outputs: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("user_id", "number", name="uq_plan_version_number"),)


class Alert(Base):
    """A raised alert. One row per (user, dedupe_key); its status carries the lifecycle:
    open -> dismissed | snoozed | acted | resolved (condition went away)."""

    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: f"alt_{uuid.uuid4().hex[:16]}")
    user_id: Mapped[str] = mapped_column(String(128), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    dedupe_key: Mapped[str] = mapped_column(String(160), nullable=False)
    rule_id: Mapped[str] = mapped_column(String(40), nullable=False)
    family: Mapped[str] = mapped_column(String(20), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    action_label: Mapped[Optional[str]] = mapped_column(String(80))
    action_link: Mapped[Optional[str]] = mapped_column(String(160))
    impact_paise: Mapped[Optional[int]] = mapped_column(BigInteger)
    rank_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    data: Mapped[Optional[dict]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    dismissed_severity: Mapped[Optional[str]] = mapped_column(String(16))
    snoozed_until: Mapped[Optional[date]] = mapped_column(Date)
    notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    acted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("user_id", "dedupe_key", name="uq_alert_dedupe"),)
