"""
Unit tests for CachedTool wrapper.

Tests caching functionality:
- Cache hit/miss scenarios
- Skip cache behavior
- TTL priority
- Graceful error handling
- Cache key generation
"""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.tools.base import BaseTool, ToolMetadata
from app.tools.cached_tool import CachedTool


class MockTool(BaseTool):
    """Simple mock tool for testing."""

    def __init__(self, cache_ttl: int | None = None, skip_cache: bool = False) -> None:
        self._cache_ttl = cache_ttl
        self._skip_cache = skip_cache
        self.execute_count = 0  # Track how many times execute was called
        super().__init__()

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="mock_tool",
            description="Mock tool for testing",
            parameters={
                "type": "object",
                "properties": {"input": {"type": "string", "description": "Input value"}},
                "required": ["input"],
            },
            category="utility",
            cache_ttl=self._cache_ttl,
            skip_cache=self._skip_cache,
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Execute and track call count."""
        self.execute_count += 1
        input_value = kwargs.get("input", "")
        return {"result": f"processed_{input_value}", "count": self.execute_count}


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Create mock Redis client."""
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.setex = AsyncMock(return_value=True)
    redis_mock.delete = AsyncMock(return_value=True)
    redis_mock.aclose = AsyncMock()
    return redis_mock


@pytest.fixture
def mock_settings() -> MagicMock:
    """Create mock settings."""
    settings = MagicMock()
    settings.REDIS_URL = "redis://localhost:6379"
    settings.CACHE_TTL_SECONDS = 3600
    return settings


class TestCachedToolBasics:
    """Basic CachedTool functionality tests."""

    @patch("app.tools.cached_tool.redis.from_url")
    @patch("app.tools.cached_tool.get_settings")
    def test_init_with_default_ttl(
        self, mock_get_settings: MagicMock, mock_from_url: MagicMock
    ) -> None:
        """Test initialization with default TTL from settings."""
        mock_settings = MagicMock()
        mock_settings.REDIS_URL = "redis://localhost:6379"
        mock_settings.CACHE_TTL_SECONDS = 3600
        mock_get_settings.return_value = mock_settings

        tool = MockTool()
        cached_tool = CachedTool(tool)

        assert cached_tool.tool == tool
        assert cached_tool.ttl_seconds == 3600
        mock_from_url.assert_called_once()

    @patch("app.tools.cached_tool.redis.from_url")
    @patch("app.tools.cached_tool.get_settings")
    def test_init_with_tool_metadata_ttl(
        self, mock_get_settings: MagicMock, mock_from_url: MagicMock
    ) -> None:
        """Test TTL priority: tool metadata over global default."""
        mock_settings = MagicMock()
        mock_settings.REDIS_URL = "redis://localhost:6379"
        mock_settings.CACHE_TTL_SECONDS = 3600
        mock_get_settings.return_value = mock_settings

        tool = MockTool(cache_ttl=600)  # Tool wants 10 minutes
        cached_tool = CachedTool(tool)

        assert cached_tool.ttl_seconds == 600

    @patch("app.tools.cached_tool.redis.from_url")
    @patch("app.tools.cached_tool.get_settings")
    def test_init_with_constructor_ttl(
        self, mock_get_settings: MagicMock, mock_from_url: MagicMock
    ) -> None:
        """Test TTL priority: constructor arg over everything."""
        mock_settings = MagicMock()
        mock_settings.REDIS_URL = "redis://localhost:6379"
        mock_settings.CACHE_TTL_SECONDS = 3600
        mock_get_settings.return_value = mock_settings

        tool = MockTool(cache_ttl=600)
        cached_tool = CachedTool(tool, ttl_seconds=300)  # Constructor override

        assert cached_tool.ttl_seconds == 300

    def test_get_metadata(self) -> None:
        """Test metadata passthrough."""
        with (
            patch("app.tools.cached_tool.redis.from_url"),
            patch("app.tools.cached_tool.get_settings"),
        ):
            tool = MockTool()
            cached_tool = CachedTool(tool)

            metadata = cached_tool.get_metadata()
            assert metadata.name == "mock_tool"
            assert metadata.category == "utility"


class TestCacheKeyGeneration:
    """Test cache key generation logic."""

    @patch("app.tools.cached_tool.redis.from_url")
    @patch("app.tools.cached_tool.get_settings")
    def test_cache_key_format(self, mock_get_settings: MagicMock, mock_from_url: MagicMock) -> None:
        """Test cache key format is correct."""
        mock_settings = MagicMock()
        mock_settings.REDIS_URL = "redis://localhost:6379"
        mock_settings.CACHE_TTL_SECONDS = 3600
        mock_get_settings.return_value = mock_settings

        tool = MockTool()
        cached_tool = CachedTool(tool)

        key = cached_tool._generate_cache_key(input="test", value=123)

        assert key.startswith("tool_cache:mock_tool:")
        assert len(key.split(":")) == 3  # tool_cache:tool_name:hash

    @patch("app.tools.cached_tool.redis.from_url")
    @patch("app.tools.cached_tool.get_settings")
    def test_cache_key_parameter_order_independence(
        self, mock_get_settings: MagicMock, mock_from_url: MagicMock
    ) -> None:
        """Test that parameter order doesn't affect cache key."""
        mock_settings = MagicMock()
        mock_settings.REDIS_URL = "redis://localhost:6379"
        mock_settings.CACHE_TTL_SECONDS = 3600
        mock_get_settings.return_value = mock_settings

        tool = MockTool()
        cached_tool = CachedTool(tool)

        key1 = cached_tool._generate_cache_key(a=1, b=2, c=3)
        key2 = cached_tool._generate_cache_key(c=3, a=1, b=2)
        key3 = cached_tool._generate_cache_key(b=2, c=3, a=1)

        assert key1 == key2 == key3

    @patch("app.tools.cached_tool.redis.from_url")
    @patch("app.tools.cached_tool.get_settings")
    def test_cache_key_different_params_different_keys(
        self, mock_get_settings: MagicMock, mock_from_url: MagicMock
    ) -> None:
        """Test that different parameters generate different keys."""
        mock_settings = MagicMock()
        mock_settings.REDIS_URL = "redis://localhost:6379"
        mock_settings.CACHE_TTL_SECONDS = 3600
        mock_get_settings.return_value = mock_settings

        tool = MockTool()
        cached_tool = CachedTool(tool)

        key1 = cached_tool._generate_cache_key(input="test1")
        key2 = cached_tool._generate_cache_key(input="test2")

        assert key1 != key2


class TestCacheHitMiss:
    """Test cache hit and miss scenarios."""

    @pytest.mark.asyncio
    @patch("app.tools.cached_tool.redis.from_url")
    @patch("app.tools.cached_tool.get_settings")
    async def test_cache_miss_executes_tool(
        self, mock_get_settings: MagicMock, mock_from_url: MagicMock, mock_redis: AsyncMock
    ) -> None:
        """Test cache miss executes original tool."""
        mock_settings = MagicMock()
        mock_settings.REDIS_URL = "redis://localhost:6379"
        mock_settings.CACHE_TTL_SECONDS = 3600
        mock_get_settings.return_value = mock_settings
        mock_from_url.return_value = mock_redis

        mock_redis.get.return_value = None  # Cache miss

        tool = MockTool()
        cached_tool = CachedTool(tool)

        result = await cached_tool.execute(input="test")

        assert result == {"result": "processed_test", "count": 1}
        assert tool.execute_count == 1
        mock_redis.get.assert_called_once()
        mock_redis.setex.assert_called_once()  # Should store result

    @pytest.mark.asyncio
    @patch("app.tools.cached_tool.redis.from_url")
    @patch("app.tools.cached_tool.get_settings")
    async def test_cache_hit_skips_tool(
        self, mock_get_settings: MagicMock, mock_from_url: MagicMock, mock_redis: AsyncMock
    ) -> None:
        """Test cache hit doesn't execute original tool."""
        mock_settings = MagicMock()
        mock_settings.REDIS_URL = "redis://localhost:6379"
        mock_settings.CACHE_TTL_SECONDS = 3600
        mock_get_settings.return_value = mock_settings
        mock_from_url.return_value = mock_redis

        cached_result = {"result": "cached_value", "count": 999}
        mock_redis.get.return_value = json.dumps(cached_result)  # Cache hit

        tool = MockTool()
        cached_tool = CachedTool(tool)

        result = await cached_tool.execute(input="test")

        assert result == cached_result
        assert tool.execute_count == 0  # Tool NOT executed
        mock_redis.get.assert_called_once()
        mock_redis.setex.assert_not_called()  # No write on hit

    @pytest.mark.asyncio
    @patch("app.tools.cached_tool.redis.from_url")
    @patch("app.tools.cached_tool.get_settings")
    async def test_cache_stores_with_correct_ttl(
        self, mock_get_settings: MagicMock, mock_from_url: MagicMock, mock_redis: AsyncMock
    ) -> None:
        """Test cache stores result with correct TTL."""
        mock_settings = MagicMock()
        mock_settings.REDIS_URL = "redis://localhost:6379"
        mock_settings.CACHE_TTL_SECONDS = 3600
        mock_get_settings.return_value = mock_settings
        mock_from_url.return_value = mock_redis

        mock_redis.get.return_value = None  # Cache miss

        tool = MockTool(cache_ttl=600)
        cached_tool = CachedTool(tool)

        await cached_tool.execute(input="test")

        # Check setex was called with correct TTL
        call_args = mock_redis.setex.call_args
        assert call_args[0][1] == 600  # Second arg is TTL


class TestSkipCache:
    """Test skip_cache functionality."""

    @pytest.mark.asyncio
    @patch("app.tools.cached_tool.redis.from_url")
    @patch("app.tools.cached_tool.get_settings")
    async def test_skip_cache_never_reads_cache(
        self, mock_get_settings: MagicMock, mock_from_url: MagicMock, mock_redis: AsyncMock
    ) -> None:
        """Test skip_cache=True never reads from cache."""
        mock_settings = MagicMock()
        mock_settings.REDIS_URL = "redis://localhost:6379"
        mock_settings.CACHE_TTL_SECONDS = 3600
        mock_get_settings.return_value = mock_settings
        mock_from_url.return_value = mock_redis

        tool = MockTool(skip_cache=True)
        cached_tool = CachedTool(tool)

        result = await cached_tool.execute(input="test")

        assert result == {"result": "processed_test", "count": 1}
        assert tool.execute_count == 1
        mock_redis.get.assert_not_called()  # Should not check cache
        mock_redis.setex.assert_not_called()  # Should not write cache

    @pytest.mark.asyncio
    @patch("app.tools.cached_tool.redis.from_url")
    @patch("app.tools.cached_tool.get_settings")
    async def test_skip_cache_always_executes_tool(
        self, mock_get_settings: MagicMock, mock_from_url: MagicMock, mock_redis: AsyncMock
    ) -> None:
        """Test skip_cache=True always executes fresh."""
        mock_settings = MagicMock()
        mock_settings.REDIS_URL = "redis://localhost:6379"
        mock_settings.CACHE_TTL_SECONDS = 3600
        mock_get_settings.return_value = mock_settings
        mock_from_url.return_value = mock_redis

        tool = MockTool(skip_cache=True)
        cached_tool = CachedTool(tool)

        # Execute twice - both should hit the tool
        result1 = await cached_tool.execute(input="test")
        result2 = await cached_tool.execute(input="test")

        assert tool.execute_count == 2  # Both executions hit tool
        assert result1["count"] == 1
        assert result2["count"] == 2


class TestErrorHandling:
    """Test graceful error handling."""

    @pytest.mark.asyncio
    @patch("app.tools.cached_tool.redis.from_url")
    @patch("app.tools.cached_tool.get_settings")
    async def test_cache_read_error_falls_through(
        self, mock_get_settings: MagicMock, mock_from_url: MagicMock, mock_redis: AsyncMock
    ) -> None:
        """Test cache read errors don't break execution."""
        mock_settings = MagicMock()
        mock_settings.REDIS_URL = "redis://localhost:6379"
        mock_settings.CACHE_TTL_SECONDS = 3600
        mock_get_settings.return_value = mock_settings
        mock_from_url.return_value = mock_redis

        mock_redis.get.side_effect = Exception("Redis connection failed")

        tool = MockTool()
        cached_tool = CachedTool(tool)

        # Should still work despite Redis error
        result = await cached_tool.execute(input="test")

        assert result == {"result": "processed_test", "count": 1}
        assert tool.execute_count == 1

    @pytest.mark.asyncio
    @patch("app.tools.cached_tool.redis.from_url")
    @patch("app.tools.cached_tool.get_settings")
    async def test_cache_write_error_returns_result(
        self, mock_get_settings: MagicMock, mock_from_url: MagicMock, mock_redis: AsyncMock
    ) -> None:
        """Test cache write errors don't break execution."""
        mock_settings = MagicMock()
        mock_settings.REDIS_URL = "redis://localhost:6379"
        mock_settings.CACHE_TTL_SECONDS = 3600
        mock_get_settings.return_value = mock_settings
        mock_from_url.return_value = mock_redis

        mock_redis.get.return_value = None
        mock_redis.setex.side_effect = Exception("Redis write failed")

        tool = MockTool()
        cached_tool = CachedTool(tool)

        # Should still return result despite write error
        result = await cached_tool.execute(input="test")

        assert result == {"result": "processed_test", "count": 1}
        assert tool.execute_count == 1

    @pytest.mark.asyncio
    @patch("app.tools.cached_tool.redis.from_url")
    @patch("app.tools.cached_tool.get_settings")
    async def test_close_error_handled_gracefully(
        self, mock_get_settings: MagicMock, mock_from_url: MagicMock, mock_redis: AsyncMock
    ) -> None:
        """Test close errors are handled gracefully."""
        mock_settings = MagicMock()
        mock_settings.REDIS_URL = "redis://localhost:6379"
        mock_settings.CACHE_TTL_SECONDS = 3600
        mock_get_settings.return_value = mock_settings
        mock_from_url.return_value = mock_redis

        mock_redis.aclose.side_effect = Exception("Close failed")

        tool = MockTool()
        cached_tool = CachedTool(tool)

        # Should not raise exception
        await cached_tool.close()
        mock_redis.aclose.assert_called_once()


class TestRunMethod:
    """Test run() method with cached flag."""

    @pytest.mark.asyncio
    @patch("app.tools.cached_tool.redis.from_url")
    @patch("app.tools.cached_tool.get_settings")
    async def test_run_sets_cached_flag_on_hit(
        self, mock_get_settings: MagicMock, mock_from_url: MagicMock, mock_redis: AsyncMock
    ) -> None:
        """Test run() sets cached=True when result from cache."""
        mock_settings = MagicMock()
        mock_settings.REDIS_URL = "redis://localhost:6379"
        mock_settings.CACHE_TTL_SECONDS = 3600
        mock_get_settings.return_value = mock_settings
        mock_from_url.return_value = mock_redis

        # Simulate cache hit - get() returns cached data
        mock_redis.get.return_value = json.dumps({"result": "cached"})

        tool = MockTool()
        cached_tool = CachedTool(tool)

        result = await cached_tool.run(input="test")

        assert result.success is True
        assert result.cached is True
        assert tool.execute_count == 0  # Tool not executed (cache hit)

    @pytest.mark.asyncio
    @patch("app.tools.cached_tool.redis.from_url")
    @patch("app.tools.cached_tool.get_settings")
    async def test_run_sets_cached_flag_on_miss(
        self, mock_get_settings: MagicMock, mock_from_url: MagicMock, mock_redis: AsyncMock
    ) -> None:
        """Test run() sets cached=False when executing fresh."""
        mock_settings = MagicMock()
        mock_settings.REDIS_URL = "redis://localhost:6379"
        mock_settings.CACHE_TTL_SECONDS = 3600
        mock_get_settings.return_value = mock_settings
        mock_from_url.return_value = mock_redis

        # Simulate cache miss - get() returns None
        mock_redis.get.return_value = None

        tool = MockTool()
        cached_tool = CachedTool(tool)

        result = await cached_tool.run(input="test")

        assert result.success is True
        assert result.cached is False
        assert tool.execute_count == 1  # Tool executed (cache miss)

    @pytest.mark.asyncio
    @patch("app.tools.cached_tool.redis.from_url")
    @patch("app.tools.cached_tool.get_settings")
    async def test_run_with_corrupted_cache_data(
        self, mock_get_settings: MagicMock, mock_from_url: MagicMock, mock_redis: AsyncMock
    ) -> None:
        """Test run() handles corrupted cache data gracefully."""
        mock_settings = MagicMock()
        mock_settings.REDIS_URL = "redis://localhost:6379"
        mock_settings.CACHE_TTL_SECONDS = 3600
        mock_get_settings.return_value = mock_settings
        mock_from_url.return_value = mock_redis

        # Simulate corrupted JSON in cache
        mock_redis.get.return_value = "invalid json {"

        tool = MockTool()
        cached_tool = CachedTool(tool)

        result = await cached_tool.run(input="test")

        assert result.success is True
        assert result.cached is False  # Corrupted cache = fresh execution
        assert tool.execute_count == 1  # Tool executed
        mock_redis.delete.assert_called_once()  # Corrupted key deleted


class TestIntegration:
    """Integration tests with real-like scenarios."""

    @pytest.mark.asyncio
    @patch("app.tools.cached_tool.redis.from_url")
    @patch("app.tools.cached_tool.get_settings")
    async def test_multiple_calls_with_same_params(
        self, mock_get_settings: MagicMock, mock_from_url: MagicMock, mock_redis: AsyncMock
    ) -> None:
        """Test multiple calls with same params use cache."""
        mock_settings = MagicMock()
        mock_settings.REDIS_URL = "redis://localhost:6379"
        mock_settings.CACHE_TTL_SECONDS = 3600
        mock_get_settings.return_value = mock_settings
        mock_from_url.return_value = mock_redis

        # First call: cache miss
        # Second call: cache hit
        mock_redis.get.side_effect = [None, json.dumps({"result": "processed_test", "count": 1})]

        tool = MockTool()
        cached_tool = CachedTool(tool)

        result1 = await cached_tool.execute(input="test")
        result2 = await cached_tool.execute(input="test")

        assert tool.execute_count == 1  # Only executed once
        assert result1 == result2

    @pytest.mark.asyncio
    @patch("app.tools.cached_tool.redis.from_url")
    @patch("app.tools.cached_tool.get_settings")
    async def test_different_params_execute_separately(
        self, mock_get_settings: MagicMock, mock_from_url: MagicMock, mock_redis: AsyncMock
    ) -> None:
        """Test different parameters execute separately."""
        mock_settings = MagicMock()
        mock_settings.REDIS_URL = "redis://localhost:6379"
        mock_settings.CACHE_TTL_SECONDS = 3600
        mock_get_settings.return_value = mock_settings
        mock_from_url.return_value = mock_redis

        mock_redis.get.return_value = None  # Always miss

        tool = MockTool()
        cached_tool = CachedTool(tool)

        result1 = await cached_tool.execute(input="test1")
        result2 = await cached_tool.execute(input="test2")

        assert tool.execute_count == 2  # Both executed
        assert result1["result"] == "processed_test1"
        assert result2["result"] == "processed_test2"
