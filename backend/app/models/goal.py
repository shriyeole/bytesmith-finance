"""FinancialGoal SQLAlchemy ORM model for ByteSmiths Finance Copilot."""

from datetime import date, datetime, timezone
import uuid
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class FinancialGoal(Base):
    """Stores a financial goal with allocated savings and target deadline.

    Enforces at most one 'ACTIVE' goal per user using a SQLite partial unique index.
    All monetary amounts are stored strictly as integer paise.
    """

    __tablename__ = "financial_goals"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"goal_{uuid.uuid4().hex[:12]}"
    )
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("user_profiles.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    target_amount_paise: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    target_date: Mapped[date] = mapped_column(
        Date, nullable=False
    )
    requested_allocated_savings_paise: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    permitted_allocated_savings_paise: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    is_allocation_capped: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="ACTIVE"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user: Mapped["UserProfile"] = relationship(back_populates="goals")

    __table_args__ = (
        # Enforces at most one active goal per user at the database engine level
        Index(
            "uq_user_active_goal",
            "user_id",
            unique=True,
            sqlite_where=text("status = 'ACTIVE'"),
        ),
    )

    @property
    def net_funding_gap_paise(self) -> int:
        """Calculate unallocated balance needed to achieve goal target."""
        return max(0, self.target_amount_paise - self.permitted_allocated_savings_paise)
