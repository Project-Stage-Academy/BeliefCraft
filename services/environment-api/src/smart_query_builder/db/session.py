from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from packages.database.src.db_engine import get_engine as get_database_engine

_ENGINE: Engine | None = None
_SESSION_FACTORY: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """
    Return a cached SQLAlchemy engine from shared database package.
    """
    global _ENGINE, _SESSION_FACTORY

    if _ENGINE is None:
        _ENGINE = get_database_engine()

    if _SESSION_FACTORY is None:
        _SESSION_FACTORY = sessionmaker(
            bind=_ENGINE,
            autoflush=False,
            autocommit=False,
            future=True,
        )

    return _ENGINE


@contextmanager
def get_session() -> Iterator[Session]:
    """
    Context manager that yields a SQLAlchemy session.
    """
    if _SESSION_FACTORY is None:
        get_engine()

    if _SESSION_FACTORY is None:
        raise RuntimeError("Session factory is not initialized.")

    session = _SESSION_FACTORY()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
