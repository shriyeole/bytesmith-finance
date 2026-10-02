import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.routers import goal_router, profile_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle event handler for database initialization."""
    if os.getenv("TESTING") != "1" and os.getenv("ENVIRONMENT") != "test":
        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="ByteSmiths — Personal Finance Copilot API",
    version="0.1.0",
    description="Deterministic cash flow, financial goal feasibility, and scenario testing engine.",
    lifespan=lifespan,
)

# Enable CORS for local React development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(profile_router)
app.include_router(goal_router)


@app.get("/health")
def health_check():
    """Health check endpoint to verify backend service readiness."""
    return {
        "status": "ok",
        "app": "ByteSmiths Finance Copilot",
        "version": "0.1.0",
    }
