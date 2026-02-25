"""
Database testing fixtures using Testcontainers and SQLAlchemy.

Functions:
- db_engine: Session-scoped fixture that provisions a PostgreSQL
    container and initializes the schema.
- db_session: Function-scoped fixture providing an isolated SQLAlchemy
    session with automatic transaction rollback.
"""

import contextlib
import json
import os
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from database.base import Base
from environment_api.data_generator.world_builder import WorldBuilder
from environment_api.main import app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from testcontainers.core.wait_strategies import LogMessageWaitStrategy
from testcontainers.postgres import PostgresContainer

docker_config_dir = tempfile.mkdtemp()
config_file = Path(docker_config_dir) / "config.json"

with Path.open(config_file, "w") as f:
    json.dump({"credsStore": "", "credHelpers": {}, "auths": {}}, f)

os.environ["DOCKER_CONFIG"] = docker_config_dir


@pytest.fixture(scope="session")
def db_engine():
    """
    Provisions a temporary PostgreSQL container for the test session.
    Creates all database tables defined in Base.metadata and drops them on teardown.
    """
    postgres = PostgresContainer("postgres:15-alpine")
    postgres.waiting_for(LogMessageWaitStrategy("database system is ready to accept connections"))

    with postgres as pg:
        engine = create_engine(pg.get_connection_url())

        Base.metadata.create_all(engine)

        yield engine

        Base.metadata.drop_all(engine)


# conftest.py


@pytest.fixture(scope="function")
def db_session(db_engine) -> Generator[Session, None, None]:
    """
    Provides a transactional SQLAlchemy session for a single test.
    Uses a sub-transaction (savepoint) to allow application-level commits
    while ensuring the test always rolls back to a clean state.
    """
    connection = db_engine.connect()
    # Start a root transaction
    transaction = connection.begin()

    # Create session bound to the connection
    # expire_on_commit=False is crucial so you can inspect objects after the test
    session_local = sessionmaker(
        bind=connection, autocommit=False, autoflush=False, expire_on_commit=False
    )
    session = session_local()

    # Begin a nested transaction (SAVEPOINT)
    # This allows app code to call session.commit() without actual persistence
    session.begin_nested()

    @pytest.hookimpl(tryfirst=True)
    def on_rollback():
        if not session.is_active:
            session.begin_nested()

    yield session

    session.close()

    # Check if transaction is still active before rolling back to avoid the SAWarning
    if transaction.is_active:
        transaction.rollback()

    connection.close()


@pytest.fixture(scope="function")
def client(db_session: Session) -> TestClient:
    """
    Provides a FastAPI TestClient with an automatically patched database session.

    Why this is important: Because the API uses `with get_session():` directly
    inside the tool modules, we must intercept those specific imports so the
    API hits your isolated test transaction instead of spinning up a new one.
    """

    @contextlib.contextmanager
    def mock_get_session():
        yield db_session

    # Stack patches for every file where `get_session` is imported and used
    patches = [
        patch(
            "environment_api.smart_query_builder.tools.inventory_tools.get_session",
            mock_get_session,
        ),
        patch(
            "environment_api.smart_query_builder.tools.order_tools.get_session", mock_get_session
        ),
        patch(
            "environment_api.smart_query_builder.tools.shipment_tools.get_session", mock_get_session
        ),
        patch(
            "environment_api.smart_query_builder.tools.observation_tools.get_session",
            mock_get_session,
        ),
    ]

    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        yield TestClient(app)


@pytest.fixture(scope="function")
def seed_base_world(db_session: Session) -> dict[str, Any]:
    """
    Orchestrates a minimalist but complete simulation world.

    Instead of manual inserts, it uses WorldBuilder with a count of 1
    to ensure all complex logistics entities (Routes, LeadtimeModels)
    are topologically correct while remaining extremely fast (<50ms).
    """
    builder = WorldBuilder(session=db_session, seed=42)

    builder.create_warehouses(count=1)
    builder.create_products(count=1)
    builder.create_suppliers(count=1)
    builder.create_logistics_network()

    db_session.flush()

    warehouse = builder.warehouses[0]
    product = builder.products[0]
    supplier = builder.suppliers[0]

    from database.enums import LocationType

    dock = next(loc for loc in warehouse.locations if loc.type == LocationType.DOCK)

    return {
        "warehouse": warehouse,
        "dock": dock,
        "product": product,
        "supplier": supplier,
        "builder": builder,
    }
