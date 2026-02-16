from pydantic import BaseModel, ConfigDict, Field


class CapacityRangeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capacity_min: int = Field(ge=1)
    capacity_max: int = Field(ge=1)


class CountCapacityConfig(CapacityRangeConfig):
    model_config = ConfigDict(extra="forbid")
    count_min: int = Field(ge=1)
    count_max: int = Field(ge=1)


class SensorProfileConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    weight: float = Field(ge=0.0)
    noise_min: float = Field(ge=0.0, le=1.0)
    noise_max: float = Field(ge=0.0, le=1.0)
    missing_min: float = Field(ge=0.0, le=1.0)
    missing_max: float = Field(ge=0.0, le=1.0)


class SensorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attach_probability: float = Field(default=0.2, ge=0.0, le=1.0)
    camera: SensorProfileConfig
    rfid: SensorProfileConfig


class LayoutConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dock: CapacityRangeConfig
    zone: CountCapacityConfig
    aisle: CountCapacityConfig
    sensor: SensorConfig
