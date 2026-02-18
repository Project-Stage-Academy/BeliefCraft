from typing import Literal

from common.utils.settings_base import BaseSettings
from pydantic import BaseModel, ConfigDict, Field

from .repositories import REPOSITORY_REGISTRY

LoggingLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class LoggingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: LoggingLevel = Field(default="INFO")
    fakeredis_level: LoggingLevel = Field(default="WARNING")
    docket_level: LoggingLevel = Field(default="WARNING")
    sse_level: LoggingLevel = Field(default="WARNING")


class Settings(BaseSettings):
    model_config = ConfigDict(extra="forbid")

    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    repository: Literal[*REPOSITORY_REGISTRY.keys()] = Field(default="FakeDataRepository")  # type: ignore[valid-type]
