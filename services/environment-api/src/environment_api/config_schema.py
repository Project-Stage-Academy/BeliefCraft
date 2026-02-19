from __future__ import annotations

from typing import Literal

from common.utils.settings_base import BaseSettings
from environment_api.simulation_configs.catalog import CatalogConfig
from environment_api.simulation_configs.infrastructure import InfrastructureConfig
from environment_api.simulation_configs.layout import LayoutConfig
from environment_api.simulation_configs.logistics import LogisticsConfig
from environment_api.simulation_configs.outbound import OutboundConfig
from environment_api.simulation_configs.replenishment import ReplenishmentConfig
from environment_api.simulation_configs.sensors import SensorsConfig
from environment_api.simulation_configs.world import SimulationConfig, WorldConfig
from pydantic import BaseModel, ConfigDict, Field


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="environment-api")
    env: Literal["dev", "prod", "local"] = Field(default="local")


class ServerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(default="0.0.0.0")  # noqa: S104
    port: int = Field(default=8000, ge=1, le=65535)


class LoggingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(default="INFO")


class Settings(BaseSettings):
    """
    Root config schema for environment-api.
    Matches YAML structure in services/environment-api/config/*.yaml
    """

    app: AppConfig = Field(default_factory=AppConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    world: WorldConfig
    simulation: SimulationConfig
    catalog: CatalogConfig
    infrastructure: InfrastructureConfig
    layout: LayoutConfig
    logistics: LogisticsConfig
    outbound: OutboundConfig
    replenishment: ReplenishmentConfig
    sensors: SensorsConfig
