import os
from pathlib import Path

from packages.common.common.utils.config_loader import ConfigLoader
from .config_schema import Settings

env = os.getenv("ENV")
service_root = Path(__file__).resolve().parents[2]

settings = ConfigLoader(service_root=service_root).load(
    schema=Settings,
    env=env if env in {"dev", "prod"} else None,
    config_env_var="ENVIRONMENT_API_CONFIG",
)
