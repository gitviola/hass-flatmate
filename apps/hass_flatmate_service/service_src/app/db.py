"""Database engine and session management."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from .settings import settings


Base = declarative_base()

engine: Engine | None = None
SessionLocal: sessionmaker[Session] | None = None


def configure_engine(db_url: str | None = None) -> None:
    """Initialize SQLAlchemy engine/sessionmaker for the given database URL."""

    global engine, SessionLocal
    engine = create_engine(
        db_url or settings.db_url,
        connect_args={"check_same_thread": False},
        future=True,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def ensure_db_dir() -> None:
    """Create database parent directory when needed."""

    parent = Path(settings.db_path).parent
    parent.mkdir(parents=True, exist_ok=True)


def get_session() -> Generator[Session, None, None]:
    """Yield a database session dependency."""

    if SessionLocal is None:
        configure_engine()
    assert SessionLocal is not None
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


configure_engine()
