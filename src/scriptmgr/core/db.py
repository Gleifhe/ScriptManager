"""SQLAlchemy engine, session factory, and declarative base."""
from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        is_sqlite = settings.db_url.startswith("sqlite")
        connect_args = {"check_same_thread": False} if is_sqlite else {}
        _engine = create_engine(
            settings.db_url,
            future=True,
            connect_args=connect_args,
            pool_pre_ping=True,
        )
        if is_sqlite:
            # P4/P11: WAL journal mode + memory cache — allows concurrent readers
            # while one writer is active, drastically reducing "database is locked" errors.
            @event.listens_for(_engine, "connect")
            def _set_sqlite_pragmas(dbapi_conn, _record):
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA synchronous=NORMAL")   # safe with WAL
                cur.execute("PRAGMA cache_size=-16000")    # 16 MB page cache
                cur.execute("PRAGMA temp_store=MEMORY")
                cur.execute("PRAGMA mmap_size=134217728")  # 128 MB memory-mapped I/O
                cur.close()
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
    return _SessionLocal


@contextmanager
def session_scope() -> Iterator[Session]:
    """Context-manager session with automatic commit / rollback."""
    s = get_session_factory()()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a DB session."""
    s = get_session_factory()()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def init_db() -> None:
    """Create all tables (dev / first-run).  Use Alembic for migrations in production."""
    from . import models  # noqa: F401 — ensure all models are imported

    Base.metadata.create_all(bind=get_engine())
