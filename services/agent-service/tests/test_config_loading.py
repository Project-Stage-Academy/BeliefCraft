from pathlib import Path

import pytest
from app.config_schema import Settings
from common.utils.config_loader import ConfigLoader


@pytest.fixture
def service_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_default_config_uses_localhost_fallbacks(
    service_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ENVIRONMENT_API_URL", raising=False)
    monkeypatch.delenv("RAG_API_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)

    settings = ConfigLoader(service_root=service_root).load(
        schema=Settings,
        dotenv_mode="none",
    )

    assert settings.external_services.environment_api_url == "http://localhost:8000"
    assert settings.external_services.rag_api_url == "http://localhost:8001"
    assert settings.redis.url == "redis://localhost:6379"


def test_default_config_allows_env_overrides(
    service_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ENVIRONMENT_API_URL", "http://environment-api:8000")
    monkeypatch.setenv("RAG_API_URL", "http://rag-service:8001")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379")

    settings = ConfigLoader(service_root=service_root).load(
        schema=Settings,
        dotenv_mode="none",
    )

    assert settings.external_services.environment_api_url == "http://environment-api:8000"
    assert settings.external_services.rag_api_url == "http://rag-service:8001"
    assert settings.redis.url == "redis://redis:6379"
