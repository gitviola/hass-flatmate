"""Database engine and session management."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from .settings import settings


Base = declarative_base()

engine: Engine | None = None
SessionLocal: sessionmaker[Session] | None = None


def configure_engine(db_url: str | None = None) -> None:
    """Initialize SQLAlchemy engine/sessionmaker for the given database URL.

    SQLite serializes writes anyway, so we keep one shared connection (StaticPool)
    rather than the default pool with up to 15 idle connections. WAL + a few
    pragmas keep concurrent reads cheap and avoid disk thrash on every commit.
    """

    global engine, SessionLocal
    engine = create_engine(
        db_url or settings.db_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA temp_store=MEMORY")
            cursor.execute("PRAGMA cache_size=-2000")  # ~2 MB page cache
            cursor.execute("PRAGMA mmap_size=33554432")  # 32 MB
        finally:
            cursor.close()

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
