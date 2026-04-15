from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.tools.code_tools import PythonSandboxTool


@pytest.fixture
def mock_settings():
    with patch("app.tools.code_tools.settings") as mock:
        mock.sandbox.runner_url = "http://sandbox-runner:8080"
        mock.sandbox.timeout_seconds = 15
        yield mock


@pytest.fixture
def tool(mock_settings):
    return PythonSandboxTool()


def test_get_metadata_schema_validity(tool):
    """
    Verifies the tool's metadata matches the expected JSON Schema format for LLM consumption.
    """
    metadata = tool.get_metadata()
    assert metadata.name == "python_sandbox"
    assert metadata.category == "utility"

    props = metadata.parameters["properties"]
    assert "code" in props
    assert "data" in props
    assert props["code"]["type"] == "string"
    assert props["data"]["type"] == "object"
    assert "code" in metadata.parameters["required"]


@pytest.mark.asyncio
@patch("app.tools.code_tools.TracedHttpClient")
async def test_execute_extracts_kwargs_and_sends_http_request(mock_http_client, tool):
    """
    Tests that the async execute wrapper correctly unpacks kwargs and forms the HTTP payload.
    """
    mock_client_instance = AsyncMock()
    mock_http_client.return_value.__aenter__.return_value = mock_client_instance

    # FIX: Use MagicMock because .json() and .raise_for_status() are synchronous
    mock_response = MagicMock()
    mock_response.json.return_value = {"stdout": "hello", "stderr": "", "exit_code": 0}
    mock_client_instance.post.return_value = mock_response

    result = await tool.execute(code="print('hello')", data={"a": 1})

    mock_http_client.assert_called_once_with("http://sandbox-runner:8080", timeout=15)
    mock_client_instance.post.assert_called_once_with(
        "/run", json={"code": "print('hello')", "data": {"a": 1}}
    )
    mock_response.raise_for_status.assert_called_once()
    assert result == {"stdout": "hello", "stderr": "", "exit_code": 0}


@pytest.mark.asyncio
@patch("app.tools.code_tools.TracedHttpClient")
async def test_execute_propagates_http_errors(mock_http_client, tool):
    """
    Ensures that if the sandbox-runner service is unreachable or returns an error,
    it raises an exception rather than silently failing.
    """
    mock_client_instance = AsyncMock()
    mock_http_client.return_value.__aenter__.return_value = mock_client_instance

    # FIX: Use MagicMock here as well so the side_effect triggers immediately
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = Exception("HTTP 500 Internal Server Error")
    mock_client_instance.post.return_value = mock_response

    with pytest.raises(Exception, match="HTTP 500"):
        await tool.execute(code="print(1)")


@pytest.mark.asyncio
async def test_execute_raises_keyerror_if_code_missing(tool):
    """
    Validates that the tool fails fast if the mandatory 'code' argument is missing.
    """
    with pytest.raises(KeyError):
        await tool.execute(data={"a": 1})
