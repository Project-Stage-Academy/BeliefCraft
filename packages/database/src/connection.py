"""Compatibility layer for database connection helpers."""

from __future__ import annotations

from pathlib import Path
import sys


def _ensure_repo_root() -> None:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "packages").exists():
            if str(parent) not in sys.path:
                sys.path.insert(0, str(parent))
            return


try:
    from packages.database.src.db_config import get_env_variable, get_database_url
    from packages.database.src.db_engine import get_engine
    from packages.database.src.db_session import SessionLocal, get_db
except ModuleNotFoundError:
    _ensure_repo_root()
    from packages.database.src.db_config import get_env_variable, get_database_url
    from packages.database.src.db_engine import get_engine
    from packages.database.src.db_session import SessionLocal, get_db


__all__ = [
    "get_env_variable",
    "get_database_url",
    "get_engine",
    "SessionLocal",
    "get_db",
]

if __name__ == "__main__":
    try:
        with get_engine().connect() as connection:
            print("Successfully connected to Supabase!")
    except Exception as e:
        print(f"Connection failed: {e}")
