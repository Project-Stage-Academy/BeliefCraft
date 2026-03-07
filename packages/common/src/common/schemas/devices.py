from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

#"device_type", ("camera", "rfid_reader", "weight_sensor", "scanner")
class DeviceType(StrEnum):
    CAMERA = "camera"
    RFID_READER = "rfid_reader"
    WEIGHT_SENSOR = "weight_sensor"
    SCANNER = "scanner"

#"device_status", ("active", "offline", "maintenance")
class DeviceStatus(StrEnum):
    ACTIVE = "active"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"

class DeviceAnomalyType(StrEnum):
    OFFLINE_WITH_OBSERVATIONS = "offline_with_observations"
    ONLINE_WITHOUT_OBSERVATIONS = "online_without_observations"
    MISSING_RATE_SPIKE = "missing_rate_spike"
    LOW_CONFIDENCE = "low_confidence"

class ListSensorDevicesRequest(BaseModel):
    warehouse_id: UUID | None = None
    device_type: DeviceType | None = None
    status: DeviceStatus | None = None

    model_config = ConfigDict(extra="forbid")


class SensorDeviceRow(BaseModel):
    id: UUID
    warehouse_id: UUID
    device_type: DeviceType
    noise_sigma: float
    missing_rate: float = Field(ge=0.0, le=1.0)
    bias: float
    status: DeviceStatus

    model_config = ConfigDict(extra="forbid")


class GetSensorDeviceRequest(BaseModel):
    device_id: UUID

    model_config = ConfigDict(extra="forbid")


class GetDeviceHealthSummaryRequest(BaseModel):
    warehouse_id: UUID | None = None
    since_ts: datetime | None = None
    as_of: datetime | None = None

    model_config = ConfigDict(extra="forbid")


class DeviceHealthSummaryRow(BaseModel):
    device_id: UUID
    warehouse_id: UUID
    status: DeviceStatus
    last_seen_at: datetime | None = None
    obs_count_window: int = Field(ge=0)
    missing_count_window: int = Field(ge=0)
    observed_null_count: int = Field(ge=0)
    avg_confidence: float | None = None

    model_config = ConfigDict(extra="forbid")


class GetDeviceAnomaliesRequest(BaseModel):
    warehouse_id: UUID | None = None
    window: int = Field(default=24, ge=1, le=24 * 30)

    model_config = ConfigDict(extra="forbid")


class DeviceAnomalyRow(BaseModel):
    device_id: UUID
    warehouse_id: UUID
    status: DeviceStatus
    anomaly_types: list[DeviceAnomalyType]
    obs_count_window: int = Field(ge=0)
    missing_count_window: int = Field(ge=0)
    observed_missing_rate: float | None = None
    configured_missing_rate: float = Field(ge=0.0, le=1.0)
    avg_confidence: float | None = None
    window_hours: int = Field(ge=1, le=24 * 30)

    model_config = ConfigDict(extra="forbid")
