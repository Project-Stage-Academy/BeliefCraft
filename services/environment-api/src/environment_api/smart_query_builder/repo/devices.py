from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from common.schemas.devices import (
    DeviceStatus as SchemaDeviceStatus,
    DeviceType as SchemaDeviceType,
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
_MAX_ANOMALY_WINDOW_HOURS = 24 * 30 #30 days are max for the window size
_ALLOWED_DEVICE_TYPE_FILTERS = frozenset(device_type.value for device_type in SchemaDeviceType)
_ALLOWED_DEVICE_STATUS_FILTERS = frozenset(status.value for status in SchemaDeviceStatus)


def _load_tables(session: Session) -> dict[str, FromClause]:
    if session.get_bind() is None:
        raise RuntimeError("Database session is not bound.")

    return _DEVICE_TABLES.copy()


def _validated_device_type_filter(value: object) -> str:
    candidate = value.value if hasattr(value, "value") else value
    if not isinstance(candidate, str) or candidate not in _ALLOWED_DEVICE_TYPE_FILTERS:
        raise ValueError(f"Invalid device_type filter: {value!r}")
    return candidate


def _validated_device_status_filter(value: object) -> str:
    candidate = value.value if hasattr(value, "value") else value
    if not isinstance(candidate, str) or candidate not in _ALLOWED_DEVICE_STATUS_FILTERS:
        raise ValueError(f"Invalid status filter: {value!r}")
    return candidate


def _validate_anomaly_window_hours(window: object) -> int:
    if isinstance(window, bool) or not isinstance(window, int):
        raise ValueError(
            f"window must be an integer between 1 and {_MAX_ANOMALY_WINDOW_HOURS} hours."
        )
    if window < 1 or window > _MAX_ANOMALY_WINDOW_HOURS:
        raise ValueError(
            f"window must be between 1 and {_MAX_ANOMALY_WINDOW_HOURS} hours inclusive."
        )
    return window


def fetch_sensor_device_rows(
    session: Session,
    request: ListSensorDevicesRequest,
) -> Sequence[RowMapping]:
    device_type_filter: str | None = None
    status_filter: str | None = None

    if request.device_type is not None:
        device_type_filter = _validated_device_type_filter(request.device_type)
    if request.status is not None:
        status_filter = _validated_device_status_filter(request.status)

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
    if device_type_filter is not None:
        stmt = stmt.where(sensor_devices.c.device_type == device_type_filter)
    if status_filter is not None:
        stmt = stmt.where(sensor_devices.c.status == status_filter)

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
    window_hours = _validate_anomaly_window_hours(request.window)
    tables = _load_tables(session)
    sensor_devices = tables["sensor_devices"]
    observations = tables["observations"]

    window_end = datetime.now(UTC)
    window_start = window_end - timedelta(hours=window_hours)

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
