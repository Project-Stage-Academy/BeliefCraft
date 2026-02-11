import logging
import os
from urllib.parse import quote_plus


logger = logging.getLogger(__name__)


def get_env_variable(var_name: str) -> str:
    value = os.environ.get(var_name)
    if not value:
        logger.error("Required environment variable missing: %s", var_name)
        raise ValueError("Critical Error: Required environment variable is not set.")
    return value


def get_database_url() -> str:
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        return database_url

    db_user = get_env_variable("SUPABASE_USER")
    encoded_password = quote_plus(get_env_variable("SUPABASE_PASSWORD"))
    db_host = get_env_variable("SUPABASE_HOST")
    db_port = get_env_variable("SUPABASE_PORT")
    db_name = get_env_variable("SUPABASE_DB")

    return f"postgresql+psycopg2://{db_user}:{encoded_password}@{db_host}:{db_port}/{db_name}"


def get_connect_args() -> dict[str, object]:
    sslmode = os.environ.get("DB_SSLMODE", "require")
    return {
        "sslmode": sslmode,
        "connect_timeout": 10,
    }
