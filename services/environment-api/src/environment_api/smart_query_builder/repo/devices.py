from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from common.schemas.devices import (
    GetDeviceAnomaliesRequest,
    GetDeviceHealthSummaryRequest,
    GetSensorDeviceRequest,
    ListSensorDevicesRequest,
)
from database.observations import Observation, SensorDevice
from sqlalchemy import and_, case, func, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session
from sqlalchemy.sql.selectable import FromClause

_DEVICE_TABLES: dict[str, FromClause] = {
    "sensor_devices": SensorDevice.__table__,
    "observations": Observation.__table__,
}


def _load_tables(session: Session) -> dict[str, FromClause]:
    if session.get_bind() is None:
        raise RuntimeError("Database session is not bound.")

    return _DEVICE_TABLES.copy()


def _enum_storage_value(value: object) -> str:
    if hasattr(value, "value"):
        return str(value.value)
    if hasattr(value, "name"):
        return str(value.name).lower()

    raw = str(value)
    if "." in raw:
        raw = raw.rsplit(".", 1)[-1]
    return raw.lower()


def fetch_sensor_device_rows(
    session: Session,
    request: ListSensorDevicesRequest,
) -> Sequence[RowMapping]:
    tables = _load_tables(session)
    sensor_devices = tables["sensor_devices"]

    stmt = (
        select(
            sensor_devices.c.id.label("id"),
            sensor_devices.c.warehouse_id.label("warehouse_id"),
            sensor_devices.c.device_type.label("device_type"),
            sensor_devices.c.noise_sigma.label("noise_sigma"),
            sensor_devices.c.missing_rate.label("missing_rate"),
            sensor_devices.c.bias.label("bias"),
            sensor_devices.c.status.label("status"),
        )
        .select_from(sensor_devices)
        .order_by(sensor_devices.c.warehouse_id.asc(), sensor_devices.c.id.asc())
    )

    if request.warehouse_id:
        stmt = stmt.where(sensor_devices.c.warehouse_id == request.warehouse_id)
    if request.device_type:
        stmt = stmt.where(sensor_devices.c.device_type == _enum_storage_value(request.device_type))
    if request.status:
        stmt = stmt.where(sensor_devices.c.status == _enum_storage_value(request.status))

    return session.execute(stmt).mappings().all()


def fetch_sensor_device_row(
    session: Session,
    request: GetSensorDeviceRequest,
) -> RowMapping | None:
    tables = _load_tables(session)
    sensor_devices = tables["sensor_devices"]

    stmt = (
        select(
            sensor_devices.c.id.label("id"),
            sensor_devices.c.warehouse_id.label("warehouse_id"),
            sensor_devices.c.device_type.label("device_type"),
            sensor_devices.c.noise_sigma.label("noise_sigma"),
            sensor_devices.c.missing_rate.label("missing_rate"),
            sensor_devices.c.bias.label("bias"),
            sensor_devices.c.status.label("status"),
        )
        .select_from(sensor_devices)
        .where(sensor_devices.c.id == request.device_id)
        .limit(1)
    )

    return session.execute(stmt).mappings().one_or_none()


def fetch_device_health_summary_rows(
    session: Session,
    request: GetDeviceHealthSummaryRequest,
) -> Sequence[RowMapping]:
    tables = _load_tables(session)
    sensor_devices = tables["sensor_devices"]
    observations = tables["observations"]

    observation_join_condition: Any = observations.c.device_id == sensor_devices.c.id
    if request.since_ts:
        observation_join_condition = and_(
            observation_join_condition,
            observations.c.observed_at >= request.since_ts,
        )
    if request.as_of:
        observation_join_condition = and_(
            observation_join_condition,
            observations.c.observed_at <= request.as_of,
        )

    obs_count_expr = func.count(observations.c.id)
    missing_count_expr = func.coalesce(
        func.sum(case((observations.c.is_missing.is_(True), 1), else_=0)),
        0,
    )
    observed_null_count_expr = func.coalesce(
        func.sum(case((observations.c.observed_qty.is_(None), 1), else_=0)),
        0,
    )

    stmt = (
        select(
            sensor_devices.c.id.label("device_id"),
            sensor_devices.c.warehouse_id.label("warehouse_id"),
            sensor_devices.c.status.label("status"),
            func.max(observations.c.observed_at).label("last_seen_at"),
            obs_count_expr.label("obs_count_window"),
            missing_count_expr.label("missing_count_window"),
            observed_null_count_expr.label("observed_null_count"),
            func.avg(observations.c.confidence).label("avg_confidence"),
        )
        .select_from(sensor_devices.outerjoin(observations, observation_join_condition))
        .group_by(
            sensor_devices.c.id,
            sensor_devices.c.warehouse_id,
            sensor_devices.c.status,
        )
        .order_by(sensor_devices.c.warehouse_id.asc(), sensor_devices.c.id.asc())
    )

    if request.warehouse_id:
        stmt = stmt.where(sensor_devices.c.warehouse_id == request.warehouse_id)

    return session.execute(stmt).mappings().all()


def fetch_device_anomaly_candidate_rows(
    session: Session,
    request: GetDeviceAnomaliesRequest,
) -> Sequence[RowMapping]:
    tables = _load_tables(session)
    sensor_devices = tables["sensor_devices"]
    observations = tables["observations"]

    window_end = datetime.now(UTC)
    window_start = window_end - timedelta(hours=request.window)

    observation_join_condition = and_(
        observations.c.device_id == sensor_devices.c.id,
        observations.c.observed_at >= window_start,
        observations.c.observed_at <= window_end,
    )

    obs_count_expr = func.count(observations.c.id)
    missing_count_expr = func.coalesce(
        func.sum(case((observations.c.is_missing.is_(True), 1), else_=0)),
        0,
    )

    observed_missing_rate_expr = (
        (missing_count_expr * 1.0) / func.nullif(obs_count_expr, 0)
    ).label("observed_missing_rate")

    stmt = (
        select(
            sensor_devices.c.id.label("device_id"),
            sensor_devices.c.warehouse_id.label("warehouse_id"),
            sensor_devices.c.status.label("status"),
            obs_count_expr.label("obs_count_window"),
            missing_count_expr.label("missing_count_window"),
            observed_missing_rate_expr,
            sensor_devices.c.missing_rate.label("configured_missing_rate"),
            func.avg(observations.c.confidence).label("avg_confidence"),
        )
        .select_from(sensor_devices.outerjoin(observations, observation_join_condition))
        .group_by(
            sensor_devices.c.id,
            sensor_devices.c.warehouse_id,
            sensor_devices.c.status,
            sensor_devices.c.missing_rate,
        )
        .order_by(
            observed_missing_rate_expr.desc().nulls_last(),
            sensor_devices.c.id.asc(),
        )
    )

    if request.warehouse_id:
        stmt = stmt.where(sensor_devices.c.warehouse_id == request.warehouse_id)

    return session.execute(stmt).mappings().all()
