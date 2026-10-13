"""Authentication dependency.

Production: the frontend signs in with Firebase Auth and sends `Authorization: Bearer <ID token>`.
The token is verified with firebase-admin; the Firebase UID becomes `users.id`.

Development/test: AUTH_MODE=dev accepts `Authorization: Bearer dev:<uid>`; with no header the
request acts as DEV_DEFAULT_USER_ID. Dev mode is refused at startup in staging/production.
"""

import logging
import threading
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.models import User
from app.database import get_db

log = logging.getLogger("app.auth")
_INIT_LOCK = threading.Lock()


@dataclass(frozen=True)
class Identity:
    uid: str
    email: Optional[str] = None
    name: Optional[str] = None


_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated.",
    headers={"WWW-Authenticate": "Bearer"},
)


def _bearer(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise _UNAUTHORIZED
    return token.strip()


def _admin_credential():
    """Google credentials if the machine has them (Cloud Run always does), else anonymous.

    Verifying an ID token only needs Google's public signing keys, so a developer laptop
    without `gcloud auth application-default login` can still run with real Firebase login.
    """
    import google.auth
    from firebase_admin import credentials
    from google.auth.credentials import AnonymousCredentials
    from google.auth.exceptions import DefaultCredentialsError

    try:
        google.auth.default()
        return credentials.ApplicationDefault()
    except DefaultCredentialsError:
        class _Anonymous(credentials.Base):
            def get_credential(self):
                return AnonymousCredentials()

        log.info("No Google credentials on this machine; verifying Firebase tokens anonymously.")
        return _Anonymous()


def _verify_firebase(token: str, settings: Settings) -> Identity:
    import firebase_admin
    from firebase_admin import auth as fb_auth

    with _INIT_LOCK:  # concurrent first requests must not both initialise the app
        if not firebase_admin._apps:
            options = {"projectId": settings.firebase_project_id} if settings.firebase_project_id else None
            firebase_admin.initialize_app(credential=_admin_credential(), options=options)
    try:
        # A few seconds of leeway: a PC clock slightly behind Google's rejects fresh tokens.
        claims = fb_auth.verify_id_token(token, clock_skew_seconds=10)
    except Exception as exc:  # invalid, expired, wrong project, revoked...
        # Log the reason (never the token) so a 401 can be diagnosed from the server log.
        log.warning("Firebase token rejected: %s: %s", type(exc).__name__, exc)
        raise _UNAUTHORIZED
    return Identity(uid=claims["uid"], email=claims.get("email"), name=claims.get("name"))


def get_identity(
    authorization: Optional[str] = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> Identity:
    token = _bearer(authorization)
    if settings.auth_mode == "dev":
        if token is None:
            return Identity(uid=settings.dev_default_user_id)
        if not token.startswith("dev:") or len(token) <= 4 or len(token) > 132:
            raise _UNAUTHORIZED
        return Identity(uid=token[4:])
    if token is None:
        raise _UNAUTHORIZED
    return _verify_firebase(token, settings)


def get_current_user(identity: Identity = Depends(get_identity), db: Session = Depends(get_db)) -> User:
    """Return the User row for the caller, creating it on first sight."""
    user = db.get(User, identity.uid)
    if user is None:
        user = User(id=identity.uid, email=identity.email, display_name=identity.name)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user
