import os
from functools import lru_cache
from typing import Generator
from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

def get_env_variable(var_name: str) -> str:
    value = os.environ.get(var_name)
    if not value:
        raise ValueError(f"Critical Error: Environment variable {var_name} is not set.")
    return value

def get_database_url() -> str:
    db_user = get_env_variable("SUPABASE_USER")
    db_password = get_env_variable("SUPABASE_PASSWORD")
    db_host = get_env_variable("SUPABASE_HOST")
    db_port = get_env_variable("SUPABASE_PORT")
    db_name = get_env_variable("SUPABASE_DB")

    encoded_password = quote_plus(db_password)
    return f"postgresql+psycopg2://{db_user}:{encoded_password}@{db_host}:{db_port}/{db_name}"


@lru_cache
def get_engine():
    database_url = get_database_url()
    return create_engine(
        database_url,
        pool_size=20,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,
        pool_pre_ping=True,
        connect_args={
            "sslmode": "require",
            "connect_timeout": 10,
        },
    )


SessionLocal = sessionmaker(autocommit=False, autoflush=False)

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal(bind=get_engine())
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    try:
        with get_engine().connect() as connection:
            print("Successfully connected to Supabase!")
    except Exception as e:
        print(f"Connection failed: {e}")
