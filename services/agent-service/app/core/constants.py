"""Application constants"""

from enum import Enum


class HealthStatus(str, Enum):
    """Health check status values"""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"
    CONFIGURED = "configured"
    MISSING_KEY = "missing_key"
    UNKNOWN = "unknown"


class DependencyName(str, Enum):
    """Dependency identifiers"""
    ENVIRONMENT_API = "environment_api"
    RAG_API = "rag_api"
    REDIS = "redis"
    ANTHROPIC = "anthropic"


# HTTP
HTTP_OK_STATUS = 200
HEALTH_CHECK_TIMEOUT = 5.0

# Error messages
ERROR_PREFIX = "error: "
