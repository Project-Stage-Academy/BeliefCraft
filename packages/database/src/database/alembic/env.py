from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from logging.config import fileConfig
from pathlib import Path
from typing import Any, TypeAlias

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.exc import SQLAlchemyError

# Ensure repo root is importable when running from any working directory.
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


ConnectArgsFactory: TypeAlias = Callable[[], dict[str, Any]]
DatabaseUrlFactory: TypeAlias = Callable[[], str]


def _load_db_dependencies() -> tuple[ConnectArgsFactory, DatabaseUrlFactory, Any]:
    from database.db_config import get_connect_args, get_database_url
    from database.models import Base

    return get_connect_args, get_database_url, Base


config = context.config
logger = logging.getLogger("alembic.env")

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _resolve_database_url() -> Any:
    """Prefer runtime env DB URL, but keep ini fallback for non-connected commands."""
    default_url = config.get_main_option("sqlalchemy.url")
    try:
        return get_database_url()
    except Exception:
        return default_url


get_connect_args, get_database_url, Base = _load_db_dependencies()

config.set_main_option("sqlalchemy.url", _resolve_database_url())

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=get_connect_args(),
    )

    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
                compare_server_default=True,
            )

            with context.begin_transaction():
                context.run_migrations()
    except SQLAlchemyError:
        logger.exception("Online migrations failed due to database connectivity or SQL error.")
        raise
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
