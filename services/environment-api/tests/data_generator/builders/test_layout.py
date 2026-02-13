"""
Tests for the Layout Builders (DockBuilder and ZoneBuilder).

Focuses on validating the correct creation of location hierarchies,
location types, and the probabilistic generation of IoT sensors without
over-constraining the exact numeric values from configurations.
"""

from unittest.mock import MagicMock, patch

import pytest
from src.data_generator.builders.layout import DockBuilder, ZoneBuilder

from packages.database.src.enums import DeviceType, LocationType
from packages.database.src.models import Location, SensorDevice, Warehouse


@pytest.fixture
def mock_session():
    """Provides a mocked SQLAlchemy session."""
    return MagicMock()


@pytest.fixture
def dummy_warehouse():
    """Provides a dummy Warehouse instance for linking dependencies."""
    wh = Warehouse(name="TEST-WH", region="EU-WEST", tz="UTC")
    wh.id = "mock-uuid-1234"
    return wh


class TestDockBuilder:
    def test_build_dock_core_logic(self, mock_session, dummy_warehouse):
        """
        Verifies that a Dock is created with the correct LocationType
        and is properly linked to the parent warehouse.
        """
        builder = DockBuilder(mock_session)
        dock = builder.build(dummy_warehouse)

        # Verify core entity properties
        assert isinstance(dock, Location)
        assert dock.type == LocationType.DOCK
        assert dock.warehouse_id == dummy_warehouse.id
        assert "DOCK" in dock.code

        # Verify persistence delegation
        mock_session.add.assert_called_once_with(dock)


class TestZoneBuilder:
    @patch("src.data_generator.builders.layout.random")
    def test_build_zones_hierarchy(self, mock_random, mock_session, dummy_warehouse):
        """
        Verifies the creation of the Zone -> Aisle hierarchy.
        Mocks random to strictly control the flow and test the parent-child relationships.
        """
        # Force a predictable layout: 2 Zones, each with 2 Aisles
        mock_random.randint.side_effect = [
            2,  # zone_count
            20000,  # zone 1 capacity
            2,  # aisle_count for zone 1
            1000,  # aisle 1 capacity
            1000,  # aisle 2 capacity
            20000,  # zone 2 capacity
            2,  # aisle_count for zone 2
            1000,  # aisle 1 capacity
            1000,  # aisle 2 capacity
        ]

        # Prevent sensors from generating to keep this specific test isolated
        mock_random.random.return_value = 1.0

        builder = ZoneBuilder(mock_session)
        zones = builder.build_zones(dummy_warehouse)

        # Verify Zone generation
        assert len(zones) == 2
        assert zones[0].type == LocationType.VIRTUAL
        assert zones[1].type == LocationType.VIRTUAL
        assert "ZONE-A" in zones[0].code
        assert "ZONE-B" in zones[1].code

        # Verify total DB interactions (2 Zones + 4 Aisles = 6 locations added)
        assert mock_session.add.call_count == 6

    @patch("src.data_generator.builders.layout.settings")
    @patch("src.data_generator.builders.layout.random")
    def test_attach_sensor_trigger_success(
        self, mock_random, mock_settings, mock_session, dummy_warehouse
    ):
        """
        Verifies that a sensor is generated and attached to the warehouse
        when the random probability threshold is met.
        """
        # Set a 50% probability threshold
        mock_settings.layout.sensor.attach_probability = 0.5

        # Force random.random() to return a "success" value (<= 0.5)
        mock_random.random.return_value = 0.2
        # Force choice to predictably pick a CAMERA
        mock_random.choices.return_value = [DeviceType.CAMERA]

        builder = ZoneBuilder(mock_session)
        builder._attach_sensor(dummy_warehouse)

        # Verify a SensorDevice was added
        assert mock_session.add.call_count == 1
        added_entity = mock_session.add.call_args[0][0]

        assert isinstance(added_entity, SensorDevice)
        assert added_entity.warehouse_id == dummy_warehouse.id
        assert added_entity.device_type == DeviceType.CAMERA

    @patch("src.data_generator.builders.layout.settings")
    @patch("src.data_generator.builders.layout.random")
    def test_attach_sensor_trigger_bypass(
        self, mock_random, mock_settings, mock_session, dummy_warehouse
    ):
        """
        Verifies that NO sensor is created if the random probability check fails.
        """
        # Set a 50% probability threshold
        mock_settings.layout.sensor.attach_probability = 0.5

        # Force random.random() to return a "failure" value (> 0.5)
        mock_random.random.return_value = 0.9

        builder = ZoneBuilder(mock_session)
        builder._attach_sensor(dummy_warehouse)

        # Verify the database session was never touched
        mock_session.add.assert_not_called()
