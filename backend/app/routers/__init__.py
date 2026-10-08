"""API routers. Everything is mounted under /api/v1 by app.main."""

from fastapi import APIRouter

from app.core.router import router as account_router
from app.modules.financial_state.router import router as financial_state_router
from app.routers.goal import router as goal_router
from app.routers.profile import router as profile_router

api_router = APIRouter()
api_router.include_router(account_router)
api_router.include_router(financial_state_router)
api_router.include_router(profile_router)
api_router.include_router(goal_router)

__all__ = ["api_router", "profile_router", "goal_router"]
