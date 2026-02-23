import sys
from pathlib import Path

# Add src to sys.path to allow importing rag_service
src_path = str(Path(__file__).resolve().parents[1] / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

import pytest  # noqa: E402
from rag_service.config import Settings  # noqa: E402


@pytest.fixture
def settings():
    """Default settings for tests."""
    return Settings(repository="FakeDataRepository")
