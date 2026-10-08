import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.models  # noqa: F401  (register ORM models with Base.metadata)
from app.core.config import get_settings
from app.database import Base, engine
from app.routers import api_router

APP_VERSION = "0.2.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    testing = os.getenv("TESTING") == "1" or settings.environment == "test"
    if settings.auto_create_tables and not testing:
        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="ByteSmiths — Personal Finance Planner API",
    version=APP_VERSION,
    description="Deterministic financial state, planning and simulation engine.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Every route lives under /api so Firebase Hosting can forward /api/** to Cloud Run.
app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
@app.get("/api/health")
def health_check():
    """Health check endpoint to verify backend service readiness."""
    return {"status": "ok", "app": "ByteSmiths Finance Copilot", "version": APP_VERSION}
