"""SQLAlchemy ORM models and persistence helpers for ByteSmiths.

Importing this package registers every table with Base.metadata (used by Alembic).
"""

from app.database import Base
from app.core.models import User
from app.models.profile import DEFAULT_USER_ID, UserProfile
from app.models.goal import FinancialGoal
from app.modules.financial_state import models as _financial_state_models  # noqa: F401
from app.modules.planning import models as _planning_models  # noqa: F401

__all__ = ["Base", "DEFAULT_USER_ID", "User", "UserProfile", "FinancialGoal"]
