import os
from typing import Literal

from common.utils.settings_base import BaseSettings
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(default="agent-service")
    version: str = Field(default="0.1.0")
    api_v1_prefix: str = Field(default="/api/v1")
    env: Literal["dev", "prod", "local"] = Field(default="local")
    skills_dir: str = Field(default="skills")
    cors_origins: list[str] = Field(default=["*"])


class ServerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    host: str = Field(default="0.0.0.0")  # noqa: S104
    port: int = Field(default=8003, ge=1, le=65535)


class LoggingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(default="INFO")


class ExternalServicesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    environment_api_url: str
    rag_api_url: str


class BedrockConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    region: str = Field(default="us-east-1")
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    max_tokens: int = Field(default=4000, ge=1, le=100000)
    connect_timeout_seconds: int = Field(default=60, ge=1, le=300)
    read_timeout_seconds: int = Field(default=300, ge=1, le=900)

    aws_profile: str | None = Field(default=None)
    aws_access_key_id: str | None = Field(default=None)
    aws_secret_access_key: str | None = Field(default=None)

    @field_validator("aws_access_key_id", "aws_secret_access_key", mode="before")
    @classmethod
    def validate_remote_credentials(cls, v: str | None, info: ValidationInfo) -> str | None:
        if not v and os.getenv("ENV") == "prod":
            raise ValueError(f"{info.field_name} is required in production environment")
        return v


class RedisConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str
    cache_ttl_seconds: int = Field(default=3600, ge=0)


class AgentExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_iterations: int = Field(default=10, ge=1, le=50)
    tool_timeout_seconds: int = Field(default=30, ge=1, le=300)


class AgentModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_id: str


class EnvSubAgentModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    planner_model_id: str
    solver_model_id: str


class LangSmithConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tracing_v2: bool = Field(default=False)
    api_key: str | None = Field(default=None)
    project: str | None = Field(default=None)

class SandboxConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    image: str = Field(default="agent-sandbox-data-science")
    timeout_seconds: int = Field(default=10, ge=1, le=60)
    memory_limit: str = Field(default="256m")
    cpus: float = Field(default=0.5)
    network_disabled: bool = Field(default=True)

class Settings(BaseSettings):
    app: AppConfig = Field(default_factory=AppConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    external_services: ExternalServicesConfig
    bedrock: BedrockConfig
    redis: RedisConfig
    execution: AgentExecutionConfig
    langsmith: LangSmithConfig
    sandbox: SandboxConfig

    react_agent: AgentModelConfig
    env_sub_agent: EnvSubAgentModelConfig
