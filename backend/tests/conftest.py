"""Keep tests independent of a developer's local backend/.env (real env vars beat .env)."""
import os

os.environ.update({
    "ENVIRONMENT": "test",
    "AUTH_MODE": "dev",
    "FIREBASE_PROJECT_ID": "",
    "DATABASE_URL": "sqlite:///./test_local.db",
    "AUTO_CREATE_TABLES": "true",
})
