from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.config_schema import Settings
from app.core.constants import HealthStatus
from app.main import app
from app.services.health_checker import HealthChecker, verify_aws_credentials_at_startup
from fastapi.testclient import TestClient
from pydantic import ValidationError

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
    "execution": {},
    "langsmith": {},
    "env_sub_agent": {
        "planner_model_id": "test-planner-model",
        "solver_model_id": "test-solver-model",
    },
}


@pytest.fixture
def client() -> Iterator[TestClient]:
    with (
        patch("app.clients.rag_mcp_client.RAGMCPClient") as mock_rag_mcp_class,
        patch("app.services.health_checker.boto3") as mock_boto3,
    ):
        mock_mcp_client = AsyncMock()
        mock_rag_mcp_class.return_value = mock_mcp_client

        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {"Account": "123456789012"}
        mock_boto3.client.return_value = mock_sts

        with TestClient(app) as test_client:
            app.state.redis_client = MagicMock()
            app.state.redis_client.ping.return_value = True

            app.state.http_client = AsyncMock()
            ok_response = MagicMock()
            ok_response.status_code = 200
            app.state.http_client.get.return_value = ok_response

            yield test_client


@patch("app.api.v1.routes.health.settings", Settings(**MOCK_SETTINGS))
def test_health_endpoint_exists(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200


@patch("app.api.v1.routes.health.settings", Settings(**MOCK_SETTINGS))
def test_health_all_services_healthy(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == HealthStatus.HEALTHY


def test_health_missing_aws_config(client: TestClient) -> None:
    degraded_dict = MOCK_SETTINGS.copy()
    degraded_dict["bedrock"] = degraded_dict["bedrock"].copy()
    degraded_dict["bedrock"]["region"] = ""

    settings_obj = Settings(**degraded_dict)

    with patch("app.api.v1.routes.health.settings", settings_obj):
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json()["status"] == HealthStatus.DEGRADED


@patch("app.api.v1.routes.health.settings", Settings(**MOCK_SETTINGS))
def test_health_redis_failure(client: TestClient) -> None:
    app.state.redis_client.ping.side_effect = Exception("Connection refused")
    response = client.get("/api/v1/health")
    assert response.json()["status"] == HealthStatus.DEGRADED


# ---------------------------------------------------------------------------
# Unit tests for HealthChecker
# ---------------------------------------------------------------------------


def _make_checker() -> HealthChecker:
    return HealthChecker(Settings(**MOCK_SETTINGS), MagicMock(), AsyncMock())


@patch("app.services.health_checker.boto3")
def test_verify_credentials_success(mock_boto3: MagicMock) -> None:
    mock_boto3.client.return_value.get_caller_identity.return_value = {"Account": "123"}
    checker = _make_checker()
    assert checker._verify_aws_credentials() == HealthStatus.HEALTHY


@patch.dict("os.environ", {"ENV": "prod"})
@patch("app.services.health_checker.boto3")
def test_startup_verification_fails_fast_in_production(mock_boto3: MagicMock) -> None:
    from app.core.exceptions import ConfigurationError

    fail_dict = MOCK_SETTINGS.copy()
    fail_dict["bedrock"] = fail_dict["bedrock"].copy()
    fail_dict["bedrock"]["aws_access_key_id"] = None
    fail_dict["bedrock"]["aws_secret_access_key"] = None

    # We expect a ValidationError because Settings() won't even allow None in prod
    with pytest.raises((ConfigurationError, ValidationError)):
        settings = Settings(**fail_dict)
        verify_aws_credentials_at_startup(settings)
