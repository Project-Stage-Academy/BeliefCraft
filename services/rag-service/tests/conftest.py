import pytest
from rag_service.config import Settings


@pytest.fixture
def settings():
    """Default settings for tests."""
    return Settings(repository="FakeDataRepository")
