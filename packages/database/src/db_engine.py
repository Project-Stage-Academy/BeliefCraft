from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from packages.database.src.db_config import get_database_url, get_connect_args

_engine: Engine | None = None
_engine_config: tuple[str, tuple[tuple[str, Any], ...]] | None = None


def _normalize_connect_args(connect_args: dict[str, Any]) -> tuple[tuple[str, Any], ...]:
    return tuple(sorted(connect_args.items()))


def get_engine() -> Engine:
    global _engine, _engine_config

    database_url = get_database_url()
    connect_args = get_connect_args()
    config_key = (database_url, _normalize_connect_args(connect_args))

    if _engine is None or _engine_config != config_key:
        if _engine is not None:
            _engine.dispose()
        _engine = create_engine(
            database_url,
            pool_size=20,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=1800,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        _engine_config = config_key

    return _engine
