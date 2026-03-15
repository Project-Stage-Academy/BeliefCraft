from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from common.schemas.observed_inventory import GetObservedInventorySnapshotRequest
from database.inventory import InventoryBalance
from database.observations import Observation
from sqlalchemy import func, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session
from sqlalchemy.sql.selectable import FromClause

from ._table_utils import load_tables

_OBSERVED_INVENTORY_TABLES: dict[str, FromClause] = {
    "observations": Observation.__table__,
    "inventory_balances": InventoryBalance.__table__,
}


def _enum_storage_value(value: object) -> str:
    if hasattr(value, "value"):
        return str(value.value)
    if hasattr(value, "name"):
        return str(value.name).lower()

    raw = str(value)
    if "." in raw:
        raw = raw.rsplit(".", 1)[-1]
    return raw.lower()


def _build_latest_observations_subquery(observations: FromClause) -> Any:
    """Build subquery with the latest observation per product/location pair."""
    return select(
        observations.c.product_id,
        observations.c.location_id,
        observations.c.observed_qty,
        observations.c.confidence,
        observations.c.device_id,
        func.row_number()
        .over(
            partition_by=(observations.c.product_id, observations.c.location_id),
            order_by=(
                observations.c.observed_at.desc(),
                observations.c.confidence.desc().nulls_last(),
                observations.c.id.asc(),
            ),
        )
        .label("rn"),
    ).subquery("latest_observations")


def _build_snapshot_stmt(
    tables: Mapping[str, FromClause],
    request: GetObservedInventorySnapshotRequest,
) -> Any:
    """Build final snapshot query without executing it."""
    obs_sub = _build_latest_observations_subquery(tables["observations"])
    inv = tables["inventory_balances"]

    stmt = (
        select(
            obs_sub.c.product_id,
            obs_sub.c.location_id,
            obs_sub.c.observed_qty,
            obs_sub.c.confidence,
            obs_sub.c.device_id,
            inv.c.quality_status,
            inv.c.on_hand,
            inv.c.reserved,
        )
        .select_from(
            obs_sub.join(
                inv,
                (inv.c.product_id == obs_sub.c.product_id)
                & (inv.c.location_id == obs_sub.c.location_id),
            )
        )
        .where(obs_sub.c.rn == 1)
        .order_by(obs_sub.c.product_id.asc(), obs_sub.c.location_id.asc())
    )

    if request.quality_status_in:
        quality_values: list[Any] = [
            _enum_storage_value(status) for status in request.quality_status_in
        ]
        stmt = stmt.where(inv.c.quality_status.in_(quality_values))

    return stmt


def fetch_observed_inventory_snapshot_rows(
    session: Session,
    request: GetObservedInventorySnapshotRequest,
) -> Sequence[RowMapping]:
    """Entry point: load tables, build query, execute, return mapped rows."""
    tables = load_tables(session, _OBSERVED_INVENTORY_TABLES)
    stmt = _build_snapshot_stmt(tables, request)
    return session.execute(stmt).mappings().all()
