"""SQLAlchemy database setup — SQLite for dev, swap to PostgreSQL via env var."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Allow override via DATABASE_URL env variable for Postgres swap
_DEFAULT_DB_PATH = Path(__file__).parent.parent / "firewall.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{_DEFAULT_DB_PATH}")

# connect_args needed only for SQLite (thread safety)
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=_connect_args,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables. Called on startup."""
    from api import models  # noqa: F401 — import to register models
    Base.metadata.create_all(bind=engine)
