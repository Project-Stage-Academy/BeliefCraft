from unittest.mock import MagicMock, patch

import pytest
import structlog

# Assuming the middleware is in a module named 'common.middleware'
from common.middleware import get_client_ip, setup_logging_middleware
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    app = FastAPI()
    setup_logging_middleware(app)

    @app.get("/test")
    async def test_endpoint():
        return {"message": "success"}

    @app.get("/error")
    async def error_endpoint():
        raise ValueError("test error")

    @app.get("/health")
    async def health_endpoint():
        return {"status": "ok"}

    return app


@pytest.fixture
def client(app):
    return TestClient(app)


### Test Client IP Extraction


def test_get_client_ip_x_forwarded_for():
    request = MagicMock(spec=Request)
    request.headers = {"X-Forwarded-For": "192.168.1.1, 10.0.0.1"}
    # Splitting ensures we get the original client, not the proxy IP
    assert get_client_ip(request) == "192.168.1.1"


def test_get_client_ip_direct():
    request = MagicMock(spec=Request)
    request.headers = {}
    request.client.host = "127.0.0.1"
    assert get_client_ip(request) == "127.0.0.1"


### Test Middleware Logic


def test_middleware_adds_request_id_header(client):
    response = client.get("/test")
    assert "X-Request-ID" in response.headers
    # Verify it's a valid UUID (or at least a string)
    assert len(response.headers["X-Request-ID"]) > 0


def test_middleware_propagates_existing_request_id(client):
    request_id = "existing-id"
    response = client.get("/test", headers={"X-Request-ID": request_id})
    assert response.headers["X-Request-ID"] == request_id


def test_middleware_truncates_long_request_id(client):
    long_id = "a" * 100
    response = client.get("/test", headers={"X-Request-ID": long_id})
    assert len(response.headers["X-Request-ID"]) == 64


@patch("common.middleware.logger")
def test_middleware_logs_normal_request(mock_logger, client):
    client.get("/test")
    # debug for start, info for finish
    assert mock_logger.debug.called
    assert mock_logger.info.called

    # Check if duration was passed to info log
    args, kwargs = mock_logger.info.call_args
    assert "duration_ms" in kwargs
    assert kwargs["status_code"] == 200


@patch("common.middleware.logger")
def test_middleware_excludes_paths(mock_logger, client):
    client.get("/health")
    # Health path is in EXCLUDE_PATHS, so no logs should be triggered
    mock_logger.debug.assert_not_called()
    mock_logger.info.assert_not_called()


@patch("common.middleware.logger")
def test_middleware_logs_exception(mock_logger, client):
    with pytest.raises(ValueError):
        client.get("/error")

    # Ensure error log was called with exception info
    assert mock_logger.error.called
    args, kwargs = mock_logger.error.call_args
    assert kwargs["error"] == "test error"
    assert kwargs["exc_info"] is True


def test_contextvars_cleanup(client):
    # Verify clear_contextvars is called by checking context is empty after request
    client.get("/test")
    assert structlog.contextvars.get_contextvars() == {}
