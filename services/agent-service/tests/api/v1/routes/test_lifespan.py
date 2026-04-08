from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from app.main import app
from fastapi.testclient import TestClient


@contextmanager
def _build_test_client() -> Iterator[TestClient]:
    with (
        patch("app.clients.rag_mcp_client.RAGMCPClient") as mock_rag_mcp_class,
        patch("app.services.health_checker.boto3") as mock_boto3,
    ):
        mock_mcp_client = AsyncMock()
        mock_mcp_client.connect.side_effect = RuntimeError("All connection attempts failed")
        mock_mcp_client.close.side_effect = RuntimeError("disconnect failed")
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


def test_startup_continues_without_rag_when_cleanup_fails() -> None:
    with _build_test_client() as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
