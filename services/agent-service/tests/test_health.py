from collections.abc import Iterator
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.config import Settings, get_settings
from app.core.constants import HealthStatus
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True
        app.state.redis_client = mock_redis

        mock_http_client = AsyncMock()
        ok_response = MagicMock()
        ok_response.status_code = 200
        mock_http_client.get.return_value = ok_response
        app.state.http_client = mock_http_client
        yield test_client


def test_health_endpoint_exists(client: TestClient) -> None:
    """Health endpoint should be accessible"""
    response = client.get("/api/v1/health")
    assert response.status_code == 200


def test_health_all_services_healthy(client: TestClient) -> None:
    """Health check should return healthy when all deps are up"""

    # Mock settings
    def override_get_settings() -> Settings:
        mock_settings = MagicMock(spec=Settings)
        mock_settings.ENVIRONMENT_API_URL = "http://env-api:8001/api/v1"
        mock_settings.RAG_API_URL = "http://rag-api:8002/api/v1"
        mock_settings.REDIS_URL = "redis://localhost:6379"
        mock_settings.ANTHROPIC_API_KEY = "test-key"
        mock_settings.SERVICE_NAME = "agent-service"
        mock_settings.SERVICE_VERSION = "0.1.0"
        return cast(Settings, mock_settings)

    app.dependency_overrides[get_settings] = override_get_settings

    response = client.get("/api/v1/health")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == HealthStatus.HEALTHY
    assert data["service"] == "agent-service"
    assert "dependencies" in data
    assert data["dependencies"]["anthropic"] == HealthStatus.CONFIGURED


def test_health_missing_anthropic_key(client: TestClient) -> None:
    """Health check should show degraded when Anthropic key is missing"""

    # Mock settings with missing API key
    def override_get_settings() -> Settings:
        mock_settings = MagicMock(spec=Settings)
        mock_settings.ENVIRONMENT_API_URL = "http://env-api:8001/api/v1"
        mock_settings.RAG_API_URL = "http://rag-api:8002/api/v1"
        mock_settings.REDIS_URL = "redis://localhost:6379"
        mock_settings.ANTHROPIC_API_KEY = ""  # Missing key
        mock_settings.SERVICE_NAME = "agent-service"
        mock_settings.SERVICE_VERSION = "0.1.0"
        return cast(Settings, mock_settings)

    app.dependency_overrides[get_settings] = override_get_settings

    response = client.get("/api/v1/health")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == HealthStatus.DEGRADED
    assert data["dependencies"]["anthropic"] == HealthStatus.MISSING_KEY


def test_health_includes_version(client: TestClient) -> None:
    """Health check should include service version"""
    response = client.get("/api/v1/health")
    data = response.json()
    assert "version" in data
    assert "timestamp" in data


def test_health_redis_failure(client: TestClient) -> None:
    """Health check should show degraded when Redis is down"""

    # Mock settings
    def override_get_settings() -> Settings:
        mock_settings = MagicMock(spec=Settings)
        mock_settings.ENVIRONMENT_API_URL = "http://env-api:8001/api/v1"
        mock_settings.RAG_API_URL = "http://rag-api:8002/api/v1"
        mock_settings.REDIS_URL = "redis://localhost:6379"
        mock_settings.ANTHROPIC_API_KEY = "test-key"
        mock_settings.SERVICE_NAME = "agent-service"
        mock_settings.SERVICE_VERSION = "0.1.0"
        return cast(Settings, mock_settings)

    app.dependency_overrides[get_settings] = override_get_settings

    # Mock Redis failure
    app.state.redis_client.ping.side_effect = Exception("Connection refused")

    response = client.get("/api/v1/health")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == HealthStatus.DEGRADED
    assert "error" in data["dependencies"]["redis"]
