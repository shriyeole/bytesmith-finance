import os
import sqlite3
from typing import Generator, Optional
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DEFAULT_DATABASE_URL = "sqlite:///./finance.db"


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
    """Retrieve database URL from environment or return default SQLite URL."""
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def build_engine(database_url: Optional[str] = None):
    """Build a SQLAlchemy Engine configured for SQLite thread safety."""
    url = database_url or get_database_url()
    connect_args = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(url, connect_args=connect_args)


engine = build_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator:
    """Provide a transactional database session scope for dependency injection."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
