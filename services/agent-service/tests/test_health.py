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

    def override_get_settings() -> Settings:
        mock_settings = MagicMock(spec=Settings)
        mock_settings.ENVIRONMENT_API_URL = "http://env-api:8001/api/v1"
        mock_settings.RAG_API_URL = "http://rag-api:8002/api/v1"
        mock_settings.REDIS_URL = "redis://localhost:6379"
        mock_settings.BEDROCK_MODEL_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
        mock_settings.SERVICE_NAME = "agent-service"
        mock_settings.SERVICE_VERSION = "0.1.0"
        return cast(Settings, mock_settings)

    app.dependency_overrides[get_settings] = override_get_settings

    response = client.get("/api/v1/health")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == HealthStatus.HEALTHY
    assert data["dependencies"]["aws_bedrock"] == HealthStatus.CONFIGURED

def test_health_missing_aws_config(client: TestClient) -> None:
    """Health check should show degraded when AWS config is missing"""

    def override_get_settings() -> Settings:
        mock_settings = MagicMock(spec=Settings)
        mock_settings.ENVIRONMENT_API_URL = "http://env-api:8001/api/v1"
        mock_settings.RAG_API_URL = "http://rag-api:8002/api/v1"
        mock_settings.REDIS_URL = "redis://localhost:6379"
        mock_settings.BEDROCK_MODEL_ID = ""  # We simulate the absence of configuration
        mock_settings.SERVICE_NAME = "agent-service"
        mock_settings.SERVICE_VERSION = "0.1.0"
        return cast(Settings, mock_settings)

    app.dependency_overrides[get_settings] = override_get_settings

    response = client.get("/api/v1/health")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == HealthStatus.DEGRADED
    # Or HealthStatus.MISSING_KEY, depending on how you named the constant in app.core.constants

def test_health_redis_failure(client: TestClient) -> None:
    """Health check should show degraded when Redis is down"""

    def override_get_settings() -> Settings:
        mock_settings = MagicMock(spec=Settings)
        mock_settings.ENVIRONMENT_API_URL = "http://env-api:8001/api/v1"
        mock_settings.RAG_API_URL = "http://rag-api:8002/api/v1"
        mock_settings.REDIS_URL = "redis://localhost:6379"
        mock_settings.BEDROCK_MODEL_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
        mock_settings.SERVICE_NAME = "agent-service"
        mock_settings.SERVICE_VERSION = "0.1.0"
        return cast(Settings, mock_settings)

    app.dependency_overrides[get_settings] = override_get_settings
    app.state.redis_client.ping.side_effect = Exception("Connection refused")

    response = client.get("/api/v1/health")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == HealthStatus.DEGRADED
    assert "error" in data["dependencies"]["redis"]