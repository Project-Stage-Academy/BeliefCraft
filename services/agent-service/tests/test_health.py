from typing import Any
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, MagicMock
from app.main import app
from app.config import Settings, get_settings
from app.core.constants import HealthStatus

client = TestClient(app)


def test_health_endpoint_exists() -> None:
    """Health endpoint should be accessible"""
    response = client.get("/api/v1/health")
    assert response.status_code == 200


@patch("app.services.health_checker.httpx.AsyncClient")
@patch("app.services.health_checker.redis.from_url")
def test_health_all_services_healthy(mock_redis: Any, mock_httpx: Any) -> None:
    """Health check should return healthy when all deps are up"""
    # Mock settings
    def override_get_settings():
        mock_settings = MagicMock(spec=Settings)
        mock_settings.ENVIRONMENT_API_URL = "http://env-api:8001/api/v1"
        mock_settings.RAG_API_URL = "http://rag-api:8002/api/v1"
        mock_settings.REDIS_URL = "redis://localhost:6379"
        mock_settings.ANTHROPIC_API_KEY = "test-key"
        mock_settings.SERVICE_NAME = "agent-service"
        mock_settings.SERVICE_VERSION = "0.1.0"
        return mock_settings
    
    app.dependency_overrides[get_settings] = override_get_settings
    
    # Mock external API calls
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_httpx.return_value.__aenter__.return_value.get.return_value = mock_response
    
    # Mock Redis
    mock_redis.return_value.ping.return_value = True
    
    response = client.get("/api/v1/health")
    
    app.dependency_overrides.clear()
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == HealthStatus.HEALTHY
    assert data["service"] == "agent-service"
    assert "dependencies" in data
    assert data["dependencies"]["anthropic"] == HealthStatus.CONFIGURED


@patch("app.services.health_checker.httpx.AsyncClient")
@patch("app.services.health_checker.redis.from_url")
def test_health_missing_anthropic_key(mock_redis: Any, mock_httpx: Any) -> None:
    """Health check should show degraded when Anthropic key is missing"""
    # Mock settings with missing API key
    def override_get_settings():
        mock_settings = MagicMock(spec=Settings)
        mock_settings.ENVIRONMENT_API_URL = "http://env-api:8001/api/v1"
        mock_settings.RAG_API_URL = "http://rag-api:8002/api/v1"
        mock_settings.REDIS_URL = "redis://localhost:6379"
        mock_settings.ANTHROPIC_API_KEY = ""  # Missing key
        mock_settings.SERVICE_NAME = "agent-service"
        mock_settings.SERVICE_VERSION = "0.1.0"
        return mock_settings
    
    app.dependency_overrides[get_settings] = override_get_settings
    
    # Mock external API calls
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_httpx.return_value.__aenter__.return_value.get.return_value = mock_response
    
    # Mock Redis
    mock_redis.return_value.ping.return_value = True
    
    response = client.get("/api/v1/health")
    
    app.dependency_overrides.clear()
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == HealthStatus.DEGRADED
    assert data["dependencies"]["anthropic"] == HealthStatus.MISSING_KEY


def test_health_includes_version() -> None:
    """Health check should include service version"""
    response = client.get("/api/v1/health")
    data = response.json()
    assert "version" in data
    assert "timestamp" in data


@patch("app.services.health_checker.httpx.AsyncClient")
@patch("app.services.health_checker.redis.from_url")
def test_health_redis_failure(mock_redis: Any, mock_httpx: Any) -> None:
    """Health check should show degraded when Redis is down"""
    # Mock settings
    def override_get_settings():
        mock_settings = MagicMock(spec=Settings)
        mock_settings.ENVIRONMENT_API_URL = "http://env-api:8001/api/v1"
        mock_settings.RAG_API_URL = "http://rag-api:8002/api/v1"
        mock_settings.REDIS_URL = "redis://localhost:6379"
        mock_settings.ANTHROPIC_API_KEY = "test-key"
        mock_settings.SERVICE_NAME = "agent-service"
        mock_settings.SERVICE_VERSION = "0.1.0"
        return mock_settings
    
    app.dependency_overrides[get_settings] = override_get_settings
    
    # Mock external API calls
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_httpx.return_value.__aenter__.return_value.get.return_value = mock_response
    
    # Mock Redis failure
    mock_redis.return_value.ping.side_effect = Exception("Connection refused")
    
    response = client.get("/api/v1/health")
    
    app.dependency_overrides.clear()
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == HealthStatus.DEGRADED
    assert "error" in data["dependencies"]["redis"]
