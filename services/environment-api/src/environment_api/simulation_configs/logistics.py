from pydantic import BaseModel, ConfigDict, Field


class LeadtimeModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    p1: float = Field(ge=0.0)
    p2: float = Field(ge=0.0)
    p_rare_delay: float = Field(ge=0.0, le=1.0)
    rare_delay_add_days: float = Field(ge=0.0)


class LogisticsModelsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    express: LeadtimeModelConfig
    standard: LeadtimeModelConfig
    ocean: LeadtimeModelConfig


class DistanceRangeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min_km: int = Field(ge=1)
    max_km: int = Field(ge=1)


class RoutingThresholdsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    truck_max_km: int = Field(gt=0)
    air_max_km: int = Field(gt=0)


class LogisticsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    models: LogisticsModelsConfig
    distance: DistanceRangeConfig
    thresholds: RoutingThresholdsConfig
