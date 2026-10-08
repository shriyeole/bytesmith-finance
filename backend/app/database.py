import sqlite3
from typing import Generator, Optional

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy ORM models."""
    pass


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable foreign key support strictly for SQLite connections."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_database_url() -> str:
    """Database URL from settings (DATABASE_URL env var), SQLite by default."""
    return get_settings().database_url


def build_engine(database_url: Optional[str] = None):
    """Build a SQLAlchemy Engine; SQLite gets thread-safety args, Postgres gets pool pre-ping."""
    url = database_url or get_database_url()
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)


engine = build_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator:
    """Provide a transactional database session scope for dependency injection."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
