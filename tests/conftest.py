import pytest
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from testcontainers.postgres import PostgresContainer
from testcontainers.core.waiting_utils import wait_for_logs

from database.base import Base

@pytest.fixture(scope="session")
def db_engine():
    with PostgresContainer("postgres:15-alpine") as postgres:
        wait_for_logs(postgres, "database system is ready to accept connections")

        engine = create_engine(postgres.get_connection_url())

        Base.metadata.create_all(engine)

        yield engine

        Base.metadata.drop_all(engine)


@pytest.fixture(scope="function")
def db_session(db_engine) -> Generator[Session, None, None]:
    connection = db_engine.connect()
    transaction = connection.begin()

    SessionLocal = sessionmaker(bind=connection, autocommit=False, autoflush=False)
    session = SessionLocal()

    yield session

    session.close()

    transaction.rollback()
    connection.close()
