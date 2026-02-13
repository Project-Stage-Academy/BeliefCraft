from __future__ import annotations

from typing import Literal

from packages.common.common.utils.settings_base import BaseSettings
from pydantic import BaseModel, ConfigDict, Field


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="environment-api")
    env: Literal["dev", "prod", "local"] = Field(default="local")


class ServerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(default="0.0.0.0")  # noqa: S104
    port: int = Field(default=8000, ge=1, le=65535)

class SimulationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_days: int = Field(default=365, gt=0)
    random_seed: int = Field(default=42)
    commit_interval: int = Field(default=10, gt=0)

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
