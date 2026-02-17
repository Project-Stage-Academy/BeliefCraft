import os
from functools import lru_cache

from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with validation"""

    # Service config
    SERVICE_NAME: str = Field(default="agent-service", description="Service name")
    SERVICE_VERSION: str = Field(default="0.1.0", description="Service version")
    API_V1_PREFIX: str = Field(default="/api/v1", description="API v1 prefix path")
    HOST: str = Field(default="0.0.0.0", description="Host to bind")  # noqa: S104
    PORT: int = Field(default=8003, ge=1, le=65535, description="Port to bind")

    # External services
    ENVIRONMENT_API_URL: str = Field(
        default="http://localhost:8000", description="Environment API base URL"
    )
    RAG_API_URL: str = Field(default="http://localhost:8001", description="RAG API base URL")

    # AWS Bedrock (Claude) config
    AWS_DEFAULT_REGION: str = Field(default="us-east-1", description="AWS Region")
    BEDROCK_MODEL_ID: str = Field(
        default="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        description="AWS Bedrock Claude model ID",
    )
    BEDROCK_TEMPERATURE: float = Field(default=0.0, ge=0.0, le=1.0, description="Model temperature")
    BEDROCK_MAX_TOKENS: int = Field(
        default=4000, ge=1, le=100000, description="Maximum tokens for completion"
    )

    AWS_PROFILE: str | None = Field(
        default=None,
        description="AWS CLI profile name (e.g. from 'aws configure --profile <name>')",
    )
    AWS_ACCESS_KEY_ID: str | None = Field(default=None)
    AWS_SECRET_ACCESS_KEY: str | None = Field(default=None)

    @field_validator("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")
    @classmethod
    def validate_remote_credentials(cls, v: str | None, info: ValidationInfo) -> str | None:
        if not v and os.getenv("ENV") == "production":
            raise ValueError(f"{info.field_name} is required in production environment")
        return v

    # Redis cache
    REDIS_URL: str = Field(default="redis://localhost:6379", description="Redis connection URL")
    CACHE_TTL_SECONDS: int = Field(default=3600, ge=0, description="Cache TTL in seconds")

    # Agent config
    MAX_ITERATIONS: int = Field(default=10, ge=1, le=50, description="Maximum agent iterations")
    TOOL_TIMEOUT_SECONDS: int = Field(
        default=30, ge=1, le=300, description="Tool execution timeout in seconds"
    )

    # CORS
    CORS_ORIGINS: list[str] = Field(
        default=["*"], description="Allowed CORS origins (comma-separated in env)"
    )

    # Logging
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level value"""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"LOG_LEVEL must be one of {valid_levels}")
        return v_upper

    model_config = {
        "env_file": ".env",
        "case_sensitive": True,
        "extra": "ignore",
    }


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
