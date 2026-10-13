"""Application settings loaded from environment variables (and an optional .env file).

Local development defaults to SQLite + dev auth so the app runs with zero setup.
Production (Cloud Run) must set ENVIRONMENT=production, DATABASE_URL and AUTH_MODE=firebase.
"""

from functools import lru_cache
from typing import Annotated, List, Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["development", "test", "staging", "production"] = "development"

    # Cloud SQL via unix socket example:
    # postgresql+psycopg://USER:PASSWORD@/DBNAME?host=/cloudsql/PROJECT:asia-south1:INSTANCE
    database_url: str = "sqlite:///./finance.db"

    # Create tables on startup without Alembic. Convenience for local SQLite only.
    auto_create_tables: bool = True

    # "firebase" verifies Firebase ID tokens; "dev" trusts "Bearer dev:<uid>" (local only).
    auth_mode: Literal["firebase", "dev"] = "dev"
    firebase_project_id: str = ""
    dev_default_user_id: str = "user_default"

    # Comma-separated in .env / env vars ("http://a,http://b"); JSON lists also work.
    cors_origins: Annotated[List[str], NoDecode] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # M6 asset-class guidance stays off in production until counsel signs off (spec §13).
    feature_allocation: bool = True

    # AI onboarding chat (Gemini). Empty key = chat switched off; the forms still work.
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    # "ai_studio" (keys from aistudio.google.com), "vertex" (keys from Cloud console Agent Platform /
    # Vertex AI, billed to Cloud credits) or "auto" (try AI Studio, then Vertex on auth/billing errors).
    gemini_endpoint: str = "auto"
    assistant_daily_messages: int = 60  # per user per 24h; bounds cost and abuse

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v):
        if isinstance(v, str) and v.strip().startswith("["):
            import json
            return json.loads(v)
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @model_validator(mode="after")
    def _guard_production(self) -> "Settings":
        if self.environment in ("staging", "production"):
            if self.auth_mode != "firebase":
                raise ValueError("AUTH_MODE must be 'firebase' outside development/test.")
            if self.database_url.startswith("sqlite"):
                raise ValueError("SQLite is not allowed outside development/test.")
            if self.auto_create_tables:
                raise ValueError("Set AUTO_CREATE_TABLES=false outside development/test; use Alembic.")
        return self

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
