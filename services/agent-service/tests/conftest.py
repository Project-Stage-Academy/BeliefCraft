import json
import os
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture(scope="session", autouse=True)
def test_settings() -> None:
    """Override settings for testing (AWS Bedrock configuration)."""
    # AWS Credentials (dummy values for testing)
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"  # noqa: S105
    os.environ["AWS_SECURITY_TOKEN"] = "testing"  # noqa: S105
    os.environ["AWS_SESSION_TOKEN"] = "testing"  # noqa: S105
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

    # Service URLs
    os.environ["ENVIRONMENT_API_URL"] = "http://localhost:8000/api/v1"
    os.environ["RAG_API_URL"] = "http://localhost:8001"
    os.environ["REDIS_URL"] = "redis://localhost:6379/1"  # Separate DB for tests


@pytest.fixture()
def mock_llm_response() -> dict[str, Any]:
    """Standard mock LLM response (unified format)."""
    return {
        "message": {
            "role": "assistant",
            "content": "Test response",
        },
        "tool_calls": [],
        "finish_reason": "stop",
        "tokens": {"prompt": 50, "completion": 30, "total": 80},
    }


@pytest.fixture(scope="session")
def mock_rag_chunks() -> list[dict]:
    """Load mock vector store data for extractor tests. Loaded once per test session."""
    # conftest.py is located at services/agent-service/tests/conftest.py
    # We want to reach: services/rag-service/src/rag_service/mock_vector_store_data.json
    conftest_dir = Path(__file__).resolve().parent
    services_dir = conftest_dir.parent.parent

    mock_data_path = (
        services_dir
        / "rag-service"
        / "src"
        / "rag_service"
        / "mock_vector_store_data.json"
    )

    with mock_data_path.open(encoding="utf-8") as f:
        return json.load(f)
