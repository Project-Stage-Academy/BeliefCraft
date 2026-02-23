import os
from pathlib import Path

from common.utils.config_loader import ConfigLoader
from common.utils.env_loader import load_service_env

from .config_schema import Settings

load_service_env(__file__)

env = os.getenv("ENV")
service_root = Path(__file__).resolve().parents[2]

settings = ConfigLoader(service_root=service_root).load(
    schema=Settings,
    env=env if env in {"dev", "prod"} else None,
    config_env_var="ENVIRONMENT_API_CONFIG",
)
