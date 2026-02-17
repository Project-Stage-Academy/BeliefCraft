"""
Tests for the InfrastructureBuilder.

Verifies the orchestration of warehouse creation, including regional distribution,
naming conventions, and the delegation to internal layout builders (Dock/Zone).
"""

from unittest.mock import MagicMock, patch

import pytest
from environment_api.data_generator.builders.infrastructure import InfrastructureBuilder


@pytest.fixture
def mock_session():
    """Provides a mocked SQLAlchemy session."""
    return MagicMock()


@pytest.fixture
def mock_settings():
    """
    Mocks the application settings for infrastructure.
    Restricts the region dictionary to two specific regions to predictably test
    the modulo cycling logic regardless of actual configuration file changes.
    """
    with patch("environment_api.data_generator.builders.infrastructure.settings") as mock_set:
        mock_set.infrastructure.region_timezones = {"EU-WEST": "UTC+1", "US-EAST": "UTC-5"}
        yield mock_set


@pytest.fixture
def builder(mock_session, mock_settings):
    """
    Initializes the InfrastructureBuilder with mocked dependencies.
    Mocks DockBuilder and ZoneBuilder to isolate the facade's orchestration logic.
    """
    with (
        patch("environment_api.data_generator.builders.infrastructure.DockBuilder"),
        patch("environment_api.data_generator.builders.infrastructure.ZoneBuilder"),
    ):
        yield InfrastructureBuilder(mock_session)


def test_create_warehouses_core_logic(builder, mock_session):
    """
    Verifies that the builder creates the correct number of warehouses,
    adds/flushes them to the database session, and correctly delegates
    the internal layout construction to the Dock and Zone builders.
    """
    count = 2
    warehouses = builder.create_warehouses(count)

    assert len(warehouses) == count
    assert mock_session.add.call_count == count
    assert mock_session.flush.call_count == count

    assert builder.dock_builder.build.call_count == count
    assert builder.zone_builder.build_zones.call_count == count


def test_create_warehouses_region_cycling_and_naming(builder):
    """
    Verifies the naming convention and the modulo-based region cycling logic.
    Ensures that properties (name, region, tz) wrap around correctly when
    the requested count exceeds the number of available regions.
    """
    count = 3
    warehouses = builder.create_warehouses(count)

    assert warehouses[0].region == "EU-WEST"
    assert warehouses[0].tz == "UTC+1"
    assert warehouses[0].name == "WH-EU-WEST-01"

    assert warehouses[1].region == "US-EAST"
    assert warehouses[1].name == "WH-US-EAST-02"

    assert warehouses[2].region == "EU-WEST"
    assert warehouses[2].tz == "UTC+1"
    assert warehouses[2].name == "WH-EU-WEST-03"
