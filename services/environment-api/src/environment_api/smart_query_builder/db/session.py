from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from database.db_engine import get_engine as get_database_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

SESSION_FACTORY = sessionmaker(
    autoflush=False,
    autocommit=False,
    future=True,
)
DEFAULT_ISOLATION_LEVEL = "REPEATABLE READ"


def get_engine() -> Engine:
    """
    Return SQLAlchemy engine from the shared database package.
    """
    engine: Engine = get_database_engine()
    return engine


@contextmanager
def get_session() -> Iterator[Session]:
    """
    Context manager that yields a SQLAlchemy session.
    """
    engine_with_isolation = get_engine().execution_options(isolation_level=DEFAULT_ISOLATION_LEVEL)
    session = SESSION_FACTORY(bind=engine_with_isolation)
    try:
        with session.begin():
            yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
