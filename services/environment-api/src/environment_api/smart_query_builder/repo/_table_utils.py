from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy import MetaData, Table
from sqlalchemy.orm import Session
from sqlalchemy.sql.selectable import FromClause


def _ensure_session_bound(session: Session) -> None:
    if session.get_bind() is None:
        raise RuntimeError("Database session is not bound.")


def load_tables(session: Session, tables: Mapping[str, FromClause]) -> dict[str, FromClause]:
    _ensure_session_bound(session)
    return dict(tables)


def load_reflected_tables(
    session: Session, table_names: Mapping[str, str]
) -> dict[str, FromClause]:
    _ensure_session_bound(session)
    bind = session.get_bind()
    metadata = MetaData()

    return {
        name: Table(table_name, metadata, autoload_with=bind)
        for name, table_name in table_names.items()
    }


def load_table(session: Session, table: FromClause) -> FromClause:
    _ensure_session_bound(session)
    return table
