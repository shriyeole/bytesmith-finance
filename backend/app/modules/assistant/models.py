"""Chat sessions for AI onboarding. One active session per user; the draft is saved only on "apply"."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import utcnow
from app.database import Base


class AssistantSession(Base):
    __tablename__ = "assistant_sessions"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: f"chat_{uuid.uuid4().hex[:16]}")
    user_id: Mapped[str] = mapped_column(String(128), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")  # active | applied | reset
    # [{"role": "user"|"assistant", "text": str, "at": iso8601}]
    messages: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    draft: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    user_turns: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
