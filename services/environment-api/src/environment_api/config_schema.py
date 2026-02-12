from __future__ import annotations

from pydantic import BaseModel, Field, ConfigDict
from typing import Literal, Optional


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="environment-api")
    env: Literal["dev", "prod", "local"] = Field(default="local")


class ServerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000, ge=1, le=65535)


class LoggingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(default="INFO")


class Settings(BaseModel):
    """
    Root config schema for environment-api.
    Matches YAML structure in services/environment-api/config/*.yaml
    """
    model_config = ConfigDict(extra="forbid")

    app: AppConfig = Field(default_factory=AppConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    # database_url: Optional[str] = None
