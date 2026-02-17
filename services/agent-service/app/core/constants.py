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


class KnowledgeGraphEntityType(StrEnum):
    """Knowledge graph entity types for RAG tools"""

    FORMULA = "formula"
    TABLE = "table"
    FIGURE = "figure"
    SECTION = "section"
    EXAMPLE = "example"
    EXERCISE = "exercise"
    ALGORITHM = "algorithm"
    APPENDIX = "appendix"


# Knowledge base
KNOWLEDGE_BASE_BOOK_NAME = "Algorithms for Decision Making"
DEFAULT_TRAVERSE_TYPES = [
    KnowledgeGraphEntityType.FORMULA.value,
    KnowledgeGraphEntityType.TABLE.value,
    KnowledgeGraphEntityType.FIGURE.value,
    KnowledgeGraphEntityType.SECTION.value,
    KnowledgeGraphEntityType.EXAMPLE.value,
    KnowledgeGraphEntityType.EXERCISE.value,
    KnowledgeGraphEntityType.ALGORITHM.value,
    KnowledgeGraphEntityType.APPENDIX.value,
]

# RAG search parameters
RAG_SEARCH_MIN_K = 1
RAG_SEARCH_DEFAULT_K = 5
RAG_SEARCH_MAX_K = 20

# HTTP
HTTP_OK_STATUS = 200
HEALTH_CHECK_TIMEOUT = 5.0

# Cache TTL constants (in seconds)
CACHE_TTL_RAG_TOOLS = 86400  # 24 hours - static knowledge from books
CACHE_TTL_HISTORY = 3600  # 1 hour - historical data doesn't change
CACHE_TTL_ANALYTICS = 600  # 10 minutes - analytics/risk calculations
CACHE_TTL_SHIPMENTS = 300  # 5 minutes - shipments change slowly

# Redis connection pool configuration
REDIS_MAX_CONNECTIONS = 10
REDIS_SOCKET_CONNECT_TIMEOUT = 5  # seconds

# Error messages
ERROR_PREFIX = "error: "
