from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import botocore.exceptions
import pytest
from app.config_schema import Settings
from app.core.constants import ERROR_PREFIX, HealthStatus
from app.main import app
from app.services.health_checker import HealthChecker, verify_aws_credentials_at_startup
from fastapi.testclient import TestClient

# Mock settings that matches the new structure for tests
MOCK_SETTINGS = {
    "app": {"name": "agent-service", "version": "0.1.0"},
    "external_services": {
        "environment_api_url": "http://env-api:8000/api/v1",
        "rag_api_url": "http://rag-api:8001/api/v1",
    },
    "redis": {"url": "redis://localhost:6379"},
    "bedrock": {
        "region": "us-east-1",
        "aws_access_key_id": "AKIAIOSFODNN7EXAMPLE",
        "aws_secret_access_key": "wJalrXUtnFEMI/EXAMPLE",
        "aws_profile": None,
    },
    "react_agent": {"model_id": "us.anthropic.claude-sonnet-4-5-20250929-v1:0"},
}


@pytest.fixture
def client() -> Iterator[TestClient]:
    # Mock RAGMCPClient and STS to prevent actual connection attempts during lifespan
    with (
        patch("app.clients.rag_mcp_client.RAGMCPClient") as mock_rag_mcp_class,
        patch("app.services.health_checker.boto3") as mock_boto3,
    ):
        mock_mcp_client = AsyncMock()
        mock_mcp_client.connect = AsyncMock()
        mock_mcp_client.close = AsyncMock()
        mock_rag_mcp_class.return_value = mock_mcp_client

        # STS returns success by default
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {"Account": "123456789012"}
        mock_boto3.Session.return_value.client.return_value = mock_sts
        mock_boto3.client.return_value = mock_sts

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


@patch("app.api.v1.routes.health.settings", Settings(**MOCK_SETTINGS))
@patch("app.services.health_checker.settings", Settings(**MOCK_SETTINGS))
def test_health_endpoint_exists(client: TestClient) -> None:
    """Health endpoint should be accessible"""
    response = client.get("/api/v1/health")
    assert response.status_code == 200


@patch("app.api.v1.routes.health.settings", Settings(**MOCK_SETTINGS))
@patch("app.services.health_checker.settings", Settings(**MOCK_SETTINGS))
def test_health_all_services_healthy(client: TestClient) -> None:
    """Health check should return healthy when all deps are up"""
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == HealthStatus.HEALTHY
    assert data["service"] == "agent-service"
    assert "dependencies" in data
    assert data["dependencies"]["aws_bedrock"] == HealthStatus.HEALTHY


def test_health_missing_aws_config(client: TestClient) -> None:
    """Health check should show degraded when AWS region or model is missing"""
    degraded_settings = MOCK_SETTINGS.copy()
    degraded_settings["bedrock"]["region"] = ""
    degraded_settings["react_agent"]["model_id"] = ""
    settings_obj = Settings(**degraded_settings)

    with (
        patch("app.api.v1.routes.health.settings", settings_obj),
        patch("app.services.health_checker.settings", settings_obj),
    ):
        response = client.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == HealthStatus.DEGRADED
        assert data["dependencies"]["aws_bedrock"] == HealthStatus.MISSING_CONFIG


@patch("app.api.v1.routes.health.settings", Settings(**MOCK_SETTINGS))
@patch("app.services.health_checker.settings", Settings(**MOCK_SETTINGS))
def test_health_redis_failure(client: TestClient) -> None:
    """Health check should show degraded when Redis is down"""
    app.state.redis_client.ping.side_effect = Exception("Connection refused")

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == HealthStatus.DEGRADED
    assert "error" in data["dependencies"]["redis"]


# ---------------------------------------------------------------------------
# Unit tests for HealthChecker._verify_aws_credentials
# ---------------------------------------------------------------------------


def _make_checker(**overrides: str) -> HealthChecker:
    """Create a HealthChecker with a minimal mock Settings."""
    defaults = MOCK_SETTINGS.copy()
    if overrides:
        # Simple override logic for testing
        if "AWS_ACCESS_KEY_ID" in overrides:
            defaults["bedrock"]["aws_access_key_id"] = overrides["AWS_ACCESS_KEY_ID"]
        if "AWS_SECRET_ACCESS_KEY" in overrides:
            defaults["bedrock"]["aws_secret_access_key"] = overrides["AWS_SECRET_ACCESS_KEY"]

    settings = Settings(**defaults)
    return HealthChecker(settings, redis_client=MagicMock(), http_client=AsyncMock())


@patch("app.services.health_checker.boto3")
def test_verify_credentials_success(mock_boto3: MagicMock) -> None:
    """STS GetCallerIdentity succeeds → HEALTHY"""
    mock_sts = MagicMock()
    mock_sts.get_caller_identity.return_value = {"Account": "123"}
    mock_boto3.client.return_value = mock_sts

    checker = _make_checker()
    assert checker._verify_aws_credentials() == HealthStatus.HEALTHY


@patch("app.services.health_checker.boto3")
def test_verify_credentials_no_creds(mock_boto3: MagicMock) -> None:
    """No credentials found → MISSING_KEY"""
    mock_boto3.client.return_value.get_caller_identity.side_effect = (
        botocore.exceptions.NoCredentialsError()
    )

    checker = _make_checker()
    assert checker._verify_aws_credentials() == HealthStatus.MISSING_KEY


@patch("app.services.health_checker.boto3")
def test_verify_credentials_invalid(mock_boto3: MagicMock) -> None:
    """Invalid credentials (ClientError) → error message"""
    error_response = {"Error": {"Code": "InvalidClientTokenId", "Message": "bad"}}
    mock_boto3.client.return_value.get_caller_identity.side_effect = (
        botocore.exceptions.ClientError(error_response, "GetCallerIdentity")
    )

    checker = _make_checker()
    result = checker._verify_aws_credentials()
    assert result.startswith(ERROR_PREFIX)
    assert "InvalidClientTokenId" in result


@patch("app.services.health_checker.boto3")
def test_verify_credentials_endpoint_unreachable(mock_boto3: MagicMock) -> None:
    """STS endpoint unreachable → graceful fallback to CONFIGURED"""
    mock_boto3.client.return_value.get_caller_identity.side_effect = (
        botocore.exceptions.EndpointConnectionError(endpoint_url="https://sts.amazonaws.com")
    )

    checker = _make_checker()
    assert checker._verify_aws_credentials() == HealthStatus.CONFIGURED


# ---------------------------------------------------------------------------
# Unit tests for verify_aws_credentials_at_startup
# ---------------------------------------------------------------------------


@patch("app.services.health_checker.boto3")
def test_startup_verification_succeeds(mock_boto3: MagicMock) -> None:
    """Startup check should pass without raising when STS succeeds."""
    mock_sts = MagicMock()
    mock_sts.get_caller_identity.return_value = {"Account": "123"}
    mock_boto3.client.return_value = mock_sts

    settings = Settings(**MOCK_SETTINGS)
    verify_aws_credentials_at_startup(settings)  # should not raise


@patch.dict("os.environ", {"ENV": "prod"})
@patch("app.services.health_checker.boto3")
def test_startup_verification_fails_fast_in_production(mock_boto3: MagicMock) -> None:
    """Startup check should raise ConfigurationError in production if creds are bad."""
    from app.core.exceptions import ConfigurationError

    mock_boto3.client.return_value.get_caller_identity.side_effect = (
        botocore.exceptions.NoCredentialsError()
    )

    fail_settings = MOCK_SETTINGS.copy()
    fail_settings["bedrock"]["aws_access_key_id"] = None
    fail_settings["bedrock"]["aws_secret_access_key"] = None
    settings = Settings(**fail_settings)

    with pytest.raises(ConfigurationError):
        verify_aws_credentials_at_startup(settings)
