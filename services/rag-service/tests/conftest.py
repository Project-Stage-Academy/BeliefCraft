import pytest  # noqa: E402
from common.logging import configure_logging  # noqa: E402
from rag_service.config import Settings  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def configure_test_logging():
    """Setup logging once for the entire test session."""
    configure_logging("rag-service-test", log_level="ERROR")


@pytest.fixture
def settings():
    """Default settings for tests."""
    return Settings(repository="FakeDataRepository")
