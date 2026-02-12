import os
from functools import lru_cache

from pydantic import Field, field_validator
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
        default="http://localhost:8000/api/v1", description="Environment API base URL"
    )
    RAG_API_URL: str = Field(default="http://localhost:8001/api/v1", description="RAG API base URL")

    # Claude (Anthropic) config
    ANTHROPIC_API_KEY: str | None = Field(default=None)

    @field_validator("ANTHROPIC_API_KEY")
    @classmethod
    def validate_api_key(cls, value: str | None, info: object) -> str | None:
        if not value and os.getenv("ENV") == "production":
            raise ValueError("ANTHROPIC_API_KEY required in production")
        return value

    ANTHROPIC_MODEL: str = Field(default="claude-sonnet-4.5", description="Claude model to use")
    ANTHROPIC_TEMPERATURE: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Model temperature"
    )
    ANTHROPIC_MAX_TOKENS: int = Field(
        default=4000, ge=1, le=100000, description="Maximum tokens for completion"
    )

    # Redis cache
    REDIS_URL: str = Field(default="redis://localhost:6379", description="Redis connection URL")
    CACHE_TTL_SECONDS: int = Field(default=3600, ge=0, description="Cache TTL in seconds")

    # Agent config
    MAX_ITERATIONS: int = Field(default=10, ge=1, le=50, description="Maximum agent iterations")
    TOOL_TIMEOUT_SECONDS: int = Field(
        default=30, ge=1, le=300, description="Tool execution timeout in seconds"
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
