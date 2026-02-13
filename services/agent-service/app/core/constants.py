"""Application constants"""

from enum import StrEnum


class HealthStatus(StrEnum):
    """Health check status values"""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"
    CONFIGURED = "configured"
    MISSING_KEY = "missing_key"
    UNKNOWN = "unknown"
    MISSING_CONFIG = "missing_config"


class DependencyName(StrEnum):
    """Dependency identifiers"""

    ENVIRONMENT_API = "environment_api"
    RAG_API = "rag_api"
    REDIS = "redis"
    AWS_BEDROCK = "aws_bedrock"


# HTTP
HTTP_OK_STATUS = 200
HEALTH_CHECK_TIMEOUT = 5.0

# Error messages
ERROR_PREFIX = "error: "
