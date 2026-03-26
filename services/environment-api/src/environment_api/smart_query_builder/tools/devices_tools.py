from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from common.schemas.common import ToolResult, build_tool_meta
from common.schemas.devices import (
    DeviceAnomalyRow,
    DeviceAnomalyType,
    DeviceHealthSummaryRow,
    DeviceStatus,
    DeviceType,
    GetDeviceAnomaliesRequest,
    GetDeviceHealthSummaryRequest,
    GetSensorDeviceRequest,
    ListSensorDevicesRequest,
    SensorDeviceRow,
)

from ..db.session import get_session
from ..repo.devices import (
    fetch_device_anomaly_candidate_rows,
    fetch_device_health_summary_rows,
    fetch_sensor_device_row,
    fetch_sensor_device_rows,
)

LOW_CONFIDENCE_THRESHOLD = 0.5


def _parse_uuid(value: str, field_name: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise ValueError(f"Invalid UUID for {field_name}: {value!r}") from exc


def _parse_optional_uuid(value: str | None, field_name: str) -> UUID | None:
    if value is None:
        return None
    return _parse_uuid(value, field_name)


def _parse_optional_device_type(value: str | DeviceType | None) -> DeviceType | None:
    if value is None:
        return None
    if isinstance(value, DeviceType):
        return value
    return DeviceType(value)


def _parse_optional_device_status(value: str | DeviceStatus | None) -> DeviceStatus | None:
    if value is None:
        return None
    if isinstance(value, DeviceStatus):
        return value
    return DeviceStatus(value)


def _to_float(value: Any, field_name: str) -> float:
    if value is None:
        raise ValueError(f"Unexpected null value for {field_name}.")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid numeric value for {field_name}: {value!r}") from exc


def _to_int(value: Any, field_name: str) -> int:
    if value is None:
        raise ValueError(f"Unexpected null value for {field_name}.")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid integer value for {field_name}: {value!r}") from exc


def _to_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _to_device_type(value: Any, field_name: str = "device_type") -> DeviceType:
    if value is None:
        raise ValueError(f"Unexpected null value for {field_name}.")

    if hasattr(value, "value"):
        raw = str(value.value)
    elif hasattr(value, "name"):
        raw = str(value.name).lower()
    else:
        raw = str(value)
        if "." in raw:
            raw = raw.rsplit(".", 1)[-1]
        raw = raw.lower()

    try:
        return DeviceType(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid device type for {field_name}: {value!r}") from exc


def _to_device_status(value: Any, field_name: str = "status") -> DeviceStatus:
    if value is None:
        raise ValueError(f"Unexpected null value for {field_name}.")

    if hasattr(value, "value"):
        raw = str(value.value)
    elif hasattr(value, "name"):
        raw = str(value.name).lower()
    else:
        raw = str(value)
        if "." in raw:
            raw = raw.rsplit(".", 1)[-1]
        raw = raw.lower()

    try:
        return DeviceStatus(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid device status for {field_name}: {value!r}") from exc


def _sensor_device_from_row(row: Any) -> SensorDeviceRow:
    return SensorDeviceRow(
        id=row["id"],
        warehouse_id=row["warehouse_id"],
        device_type=_to_device_type(row["device_type"]),
        noise_sigma=_to_float(row["noise_sigma"], "noise_sigma"),
        missing_rate=_to_float(row["missing_rate"], "missing_rate"),
        bias=_to_float(row["bias"], "bias"),
        status=_to_device_status(row["status"]),
    )


def _device_health_summary_from_row(row: Any) -> DeviceHealthSummaryRow:
    return DeviceHealthSummaryRow(
        device_id=row["device_id"],
        warehouse_id=row["warehouse_id"],
        status=_to_device_status(row["status"]),
        last_seen_at=row["last_seen_at"],
        obs_count_window=_to_int(row["obs_count_window"], "obs_count_window"),
        missing_count_window=_to_int(row["missing_count_window"], "missing_count_window"),
        observed_null_count=_to_int(row["observed_null_count"], "observed_null_count"),
        avg_confidence=_to_optional_float(row["avg_confidence"]),
    )


def _anomaly_types_for_metrics(
    status: DeviceStatus,
    obs_count_window: int,
    observed_missing_rate: float | None,
    configured_missing_rate: float,
    avg_confidence: float | None,
) -> list[DeviceAnomalyType]:
    anomaly_types: list[DeviceAnomalyType] = []
    if status == DeviceStatus.OFFLINE and obs_count_window > 0:
        anomaly_types.append(DeviceAnomalyType.OFFLINE_WITH_OBSERVATIONS)
    if status == DeviceStatus.ACTIVE and obs_count_window == 0:
        anomaly_types.append(DeviceAnomalyType.ONLINE_WITHOUT_OBSERVATIONS)
    if observed_missing_rate is not None and observed_missing_rate > configured_missing_rate:
        anomaly_types.append(DeviceAnomalyType.MISSING_RATE_SPIKE)
    if avg_confidence is not None and avg_confidence < LOW_CONFIDENCE_THRESHOLD:
        anomaly_types.append(DeviceAnomalyType.LOW_CONFIDENCE)
    return anomaly_types


def list_sensor_devices(
    warehouse_id: str | None = None,
    device_type: str | DeviceType | None = None,
    status: str | DeviceStatus | None = None,
) -> ToolResult[list[SensorDeviceRow]]:
    """
    USE THIS TOOL to list sensor devices and their calibration/status fields.
    """
    try:
        request = ListSensorDevicesRequest(
            warehouse_id=_parse_optional_uuid(warehouse_id, "warehouse_id"),
            device_type=_parse_optional_device_type(device_type),
            status=_parse_optional_device_status(status),
        )

        with get_session() as session:
            rows = fetch_sensor_device_rows(session, request)

        data = [_sensor_device_from_row(row) for row in rows]
        return ToolResult(
            data=data,
            message=(
                "No sensor devices matched filters."
                if not data
                else f"Retrieved {len(data)} sensor devices."
            ),
            meta=build_tool_meta(
                count=len(data),
                filters={
                    "warehouse_id": str(request.warehouse_id) if request.warehouse_id else None,
                    "device_type": request.device_type.value if request.device_type else None,
                    "status": request.status.value if request.status else None,
                },
            ),
        )
    except Exception as exc:
        raise RuntimeError("Unable to list sensor devices.") from exc


def get_sensor_device(
    device_id: str,
) -> ToolResult[SensorDeviceRow]:
    """
    USE THIS TOOL to retrieve one sensor device by UUID.
    """
    try:
        request = GetSensorDeviceRequest(device_id=_parse_uuid(device_id, "device_id"))

        with get_session() as session:
            row = fetch_sensor_device_row(session, request)

        if row is None:
            raise ValueError(f"Sensor device not found: {device_id}")

        return ToolResult(
            data=_sensor_device_from_row(row),
            message="Retrieved sensor device details.",
            meta=build_tool_meta(count=1, device_id=device_id),
        )
    except Exception as exc:
        raise RuntimeError("Unable to get sensor device.") from exc


def get_device_health_summary(
    warehouse_id: str | None = None,
    since_ts: datetime | None = None,
    as_of: datetime | None = None,
) -> ToolResult[list[DeviceHealthSummaryRow]]:
    """
    USE THIS TOOL for per-device health diagnostics over a selected observation window.
    """
    try:
        request = GetDeviceHealthSummaryRequest(
            warehouse_id=_parse_optional_uuid(warehouse_id, "warehouse_id"),
            since_ts=since_ts,
            as_of=as_of,
        )

        if request.since_ts and request.as_of and request.since_ts > request.as_of:
            raise ValueError("since_ts must be less than or equal to as_of")

        with get_session() as session:
            rows = fetch_device_health_summary_rows(session, request)

        data = [_device_health_summary_from_row(row) for row in rows]

        return ToolResult(
            data=data,
            message=(
                "No device health rows matched filters."
                if not data
                else f"Retrieved health summary for {len(data)} devices."
            ),
            meta=build_tool_meta(
                count=len(data),
                filters={
                    "warehouse_id": str(request.warehouse_id) if request.warehouse_id else None,
                    "since_ts": request.since_ts.isoformat() if request.since_ts else None,
                    "as_of": request.as_of.isoformat() if request.as_of else None,
                },
            ),
        )
    except Exception as exc:
        raise RuntimeError("Unable to get device health summary.") from exc


def get_device_anomalies(
    warehouse_id: str | None = None,
    window: int = 24,
) -> ToolResult[list[DeviceAnomalyRow]]:
    """
    USE THIS TOOL to detect unreliable sensor behavior in a recent time window.
    """
    try:
        request = GetDeviceAnomaliesRequest(
            warehouse_id=_parse_optional_uuid(warehouse_id, "warehouse_id"),
            window=window,
        )

        with get_session() as session:
            rows = fetch_device_anomaly_candidate_rows(session, request)

        data: list[DeviceAnomalyRow] = []
        for row in rows:
            status = _to_device_status(row["status"])
            obs_count_window = _to_int(row["obs_count_window"], "obs_count_window")
            missing_count_window = _to_int(row["missing_count_window"], "missing_count_window")
            observed_missing_rate = _to_optional_float(row["observed_missing_rate"])
            configured_missing_rate = _to_float(
                row["configured_missing_rate"], "configured_missing_rate"
            )
            avg_confidence = _to_optional_float(row["avg_confidence"])

            anomaly_types = _anomaly_types_for_metrics(
                status=status,
                obs_count_window=obs_count_window,
                observed_missing_rate=observed_missing_rate,
                configured_missing_rate=configured_missing_rate,
                avg_confidence=avg_confidence,
            )

            if not anomaly_types:
                continue

            data.append(
                DeviceAnomalyRow(
                    device_id=row["device_id"],
                    warehouse_id=row["warehouse_id"],
                    status=status,
                    anomaly_types=anomaly_types,
                    obs_count_window=obs_count_window,
                    missing_count_window=missing_count_window,
                    observed_missing_rate=observed_missing_rate,
                    configured_missing_rate=configured_missing_rate,
                    avg_confidence=avg_confidence,
                    window_hours=request.window,
                )
            )

        return ToolResult(
            data=data,
            message=(
                "No device anomalies detected."
                if not data
                else f"Detected anomalies for {len(data)} devices."
            ),
            meta=build_tool_meta(
                count=len(data),
                filters={
                    "warehouse_id": str(request.warehouse_id) if request.warehouse_id else None,
                    "window": request.window,
                },
                thresholds={
                    "low_confidence": LOW_CONFIDENCE_THRESHOLD,
                },
            ),
        )
    except Exception as exc:
        raise RuntimeError("Unable to get device anomalies.") from exc
