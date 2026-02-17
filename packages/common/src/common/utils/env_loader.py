import logging
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)


def load_service_env(
    current_file_path: str,
    markers: tuple[str, ...] = ("pyproject.toml", "requirements.txt", "package.json"),
) -> None:
    """
    Walks up from the current file to find the service root (defined by markers).
    Loads the .env file found at that specific root.

    Stops searching immediately upon finding a marker to prevent leaking
    into parent directories or the monorepo root.
    """
    path = Path(current_file_path).resolve()

    for _ in range(5):
        if any((path / marker).exists() for marker in markers):
            env_path = path / ".env"
            if env_path.exists():
                load_dotenv(env_path)
                logger.info(f"Loaded service environment from: {env_path}")
            else:
                logger.debug(f"Service root found at {path}, but no .env file exists.")
            return

        parent = path.parent
        if parent == path:
            break
        path = parent

    logger.warning(f"Could not find service root for {current_file_path}")
