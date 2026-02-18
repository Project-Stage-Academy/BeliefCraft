"""
Cached tool wrapper for adding Redis caching to any tool.

This module provides a decorator/wrapper that adds Redis-based caching
to any tool without modifying the original tool implementation.

Caching Strategy:
- RAG tools (static knowledge): 24 hours
- Historical data: 1 hour
- Analytics/risk: 10 minutes
- Real-time sensors: skip cache

Example:
    ```python
    from app.tools.cached_tool import CachedTool
    from app.tools.rag_tools import SearchKnowledgeBaseTool

    # Wrap tool with caching
    original_tool = SearchKnowledgeBaseTool()
    cached_tool = CachedTool(original_tool)

    # Use normally - caching is transparent
    result = await cached_tool.run(query="POMDP algorithms")
    print(f"Cached: {result.cached}")
    ```
"""

import hashlib
import json
from typing import Any

import redis.asyncio as redis
from app.config import get_settings
from app.core.constants import REDIS_MAX_CONNECTIONS, REDIS_SOCKET_CONNECT_TIMEOUT
from app.tools.base import BaseTool, ToolMetadata, ToolResult
from common.logging import get_logger

logger = get_logger(__name__)


class CachedTool(BaseTool):
    """
    Wrapper that adds Redis caching to any tool.

    This class wraps an existing tool and adds transparent caching
    without modifying the original tool implementation.

    Features:
    - Automatic cache key generation from parameters
    - Configurable TTL per tool or globally
    - Selective caching with skip_cache flag
    - Graceful degradation (errors don't break tool execution)
    - Cache hit/miss logging for monitoring

    Attributes:
        tool: The wrapped tool instance
        ttl_seconds: Cache TTL (priority: constructor > tool metadata > global default)
        redis_client: Redis async client for caching
        _last_was_cached: Internal flag to track if last execution used cache
    """

    def __init__(self, tool: BaseTool, ttl_seconds: int | None = None) -> None:
        """
        Initialize cached tool wrapper.

        Args:
            tool: Tool instance to wrap with caching
            ttl_seconds: Optional TTL override (seconds).
                If None, uses tool metadata or global default
        """
        self.tool = tool
        self.settings = get_settings()

        # TTL priority: 1. Constructor arg, 2. Tool metadata, 3. Global default
        tool_metadata = self.tool.get_metadata()
        self.ttl_seconds = ttl_seconds or tool_metadata.cache_ttl or self.settings.CACHE_TTL_SECONDS

        # Configure Redis connection pool explicitly for better type safety
        pool = redis.ConnectionPool.from_url(
            self.settings.REDIS_URL,
            decode_responses=True,
            max_connections=REDIS_MAX_CONNECTIONS,
            socket_keepalive=True,
            socket_connect_timeout=REDIS_SOCKET_CONNECT_TIMEOUT,
            retry_on_timeout=True,
        )
        self.redis_client = redis.Redis(connection_pool=pool)

        # Internal flag to track cache hits (thread-safe per execution)
        self._last_was_cached = False

        super().__init__()

    def get_metadata(self) -> ToolMetadata:
        """Return metadata of the wrapped tool."""
        return self.tool.get_metadata()

    def _generate_cache_key(self, **kwargs: Any) -> str:
        """
        Generate cache key from tool name and parameters.

        Uses SHA-256 hash of sorted JSON parameters to ensure:
        - Same parameters always generate same key
        - Parameter order doesn't matter
        - Strong collision resistance
        - Reasonable key length (64 hex chars)

        Args:
            **kwargs: Tool execution parameters

        Returns:
            Redis cache key string (format: "tool_cache:{tool_name}:{hash}")
        """
        tool_name = self.get_metadata().name
        # sort_keys ensures {'a':1, 'b':2} == {'b':2, 'a':1}
        params_str = json.dumps(kwargs, sort_keys=True)
        params_hash = hashlib.sha256(params_str.encode()).hexdigest()
        return f"tool_cache:{tool_name}:{params_hash}"

    async def execute(self, **kwargs: Any) -> Any:
        """
        Execute tool with caching.

        Flow:
        1. Check if caching should be skipped (skip_cache=True)
        2. Try to get result from cache
        3. On cache miss, execute original tool
        4. Store result in cache (if caching enabled)

        Args:
            **kwargs: Tool execution parameters

        Returns:
            Tool execution result (from cache or fresh execution)
        """
        metadata = self.get_metadata()

        # Reset cached flag
        self._last_was_cached = False

        # Skip caching if explicitly disabled in metadata
        if metadata.skip_cache:
            logger.debug(
                "cache_skipped_by_metadata",
                tool=metadata.name,
                reason="skip_cache=True",
            )
            return await self.tool.execute(**kwargs)

        cache_key = self._generate_cache_key(**kwargs)

        # 1. Try to get from cache
        try:
            cached_value = await self.redis_client.get(cache_key)
            if cached_value:
                # Validate cached data before returning
                try:
                    result = json.loads(cached_value)
                    # Basic validation - ensure it's a dict (expected format)
                    if not isinstance(result, dict):
                        logger.warning(
                            "cache_data_invalid",
                            tool=metadata.name,
                            reason="not_a_dict",
                        )
                        raise ValueError("Cached data is not a dictionary")

                    logger.info(
                        "tool_cache_hit",
                        tool=metadata.name,
                        cache_key=cache_key,
                    )
                    self._last_was_cached = True
                    return result
                except (json.JSONDecodeError, ValueError) as e:
                    # Corrupted cache data - delete and execute fresh
                    logger.warning(
                        "cache_data_corrupted",
                        tool=metadata.name,
                        error=str(e),
                    )
                    await self.redis_client.delete(cache_key)
        except Exception as e:
            # Graceful degradation - cache read errors don't break execution
            logger.warning(
                "cache_read_error",
                tool=metadata.name,
                error=str(e),
                error_type=type(e).__name__,
            )

        # 2. Cache miss - execute tool
        logger.info("tool_cache_miss", tool=metadata.name)
        result = await self.tool.execute(**kwargs)

        # 3. Store in cache
        try:
            # Validate result before caching
            if not isinstance(result, dict):
                logger.warning(
                    "cache_skip_invalid_result",
                    tool=metadata.name,
                    result_type=type(result).__name__,
                )
            else:
                await self.redis_client.setex(
                    cache_key,
                    self.ttl_seconds,
                    json.dumps(result),
                )
                logger.debug(
                    "cache_write_success",
                    tool=metadata.name,
                    ttl_seconds=self.ttl_seconds,
                )
        except Exception as e:
            # Graceful degradation - cache write errors don't break execution
            logger.warning(
                "cache_write_error",
                tool=metadata.name,
                error=str(e),
                error_type=type(e).__name__,
            )

        return result

    async def run(self, **kwargs: Any) -> ToolResult:
        """
        Override run to mark if result was cached.

        This method wraps the parent run() method to add cache hit
        information to the ToolResult. The cached flag is set during
        execute() to avoid race conditions.

        Args:
            **kwargs: Tool execution parameters

        Returns:
            ToolResult with cached=True if result came from cache
        """
        # Execute tool (sets _last_was_cached flag internally)
        result = await super().run(**kwargs)

        # Set cached flag from internal state (no extra Redis call)
        result.cached = self._last_was_cached

        return result

    async def close(self) -> None:
        """Close Redis connection when tool is done."""
        try:
            await self.redis_client.aclose()
        except Exception as e:
            logger.warning(
                "cache_close_error",
                error=str(e),
                error_type=type(e).__name__,
            )
