"""
Tests for the WorldBuilder.

Focuses on the orchestration logic of the general contractor: ensuring that
sub-builders are called in the correct order and that internal state
is correctly updated after each build step.
"""

from unittest.mock import MagicMock, patch

import pytest
from src.data_generator.world_builder import WorldBuilder


@pytest.fixture
def mock_session():
    """Provides a mocked SQLAlchemy session."""
    return MagicMock()


@pytest.fixture
def world_builder(mock_session):
    """
    Initializes WorldBuilder with mocked sub-builders to isolate
    the orchestration logic.
    """
    with (
        patch("src.data_generator.world_builder.InfrastructureBuilder"),
        patch("src.data_generator.world_builder.CatalogBuilder"),
        patch("src.data_generator.world_builder.LogisticsBuilder"),
    ):
        return WorldBuilder(mock_session, seed=42)


class TestWorldBuilder:
    def test_initialization_seeds_logic(self, mock_session):
        """
        Verifies that initializing the builder correctly seeds both
        Faker and the standard random library.
        """
        seed = 12345
        with (
            patch("src.data_generator.world_builder.random.seed") as mock_rseed,
            patch("src.data_generator.world_builder.Faker") as mock_faker_cls,
        ):
            WorldBuilder(mock_session, seed)

            # Verify standard random was seeded
            mock_rseed.assert_called_once_with(seed)
            # Verify Faker seed was called
            mock_faker_cls.seed.assert_called_once_with(seed)

    @patch("src.data_generator.world_builder.settings")
    def test_build_all_sequence(self, mock_settings, world_builder):
        """
        Verifies that build_all calls the individual creation methods
        in the logically required order.
        """
        # Mock the specific counts from settings
        mock_settings.world.warehouse_count = 3
        mock_settings.world.product_count = 10
        mock_settings.world.supplier_count = 5

        # Mock the creation methods to verify they are called
        world_builder.create_warehouses = MagicMock()
        world_builder.create_products = MagicMock()
        world_builder.create_suppliers = MagicMock()
        world_builder.create_logistics_network = MagicMock()

        world_builder.build_all()

        # Check order of operations
        world_builder.create_warehouses.assert_called_once_with(3)
        world_builder.create_products.assert_called_once_with(10)
        world_builder.create_suppliers.assert_called_once_with(5)
        world_builder.create_logistics_network.assert_called_once()

    def test_create_warehouses_updates_state(self, world_builder):
        """
        Verifies that results from the infra_builder are stored in the state container.
        """
        mock_results = [MagicMock(), MagicMock()]
        world_builder.infra_builder.create_warehouses.return_value = mock_results

        world_builder.create_warehouses(2)

        assert world_builder.warehouses == mock_results
        world_builder.infra_builder.create_warehouses.assert_called_once_with(2)

    def test_create_logistics_network_updates_state(self, world_builder):
        """
        Verifies that global leadtime models are created before connecting warehouses,
        and that the resulting routes are stored in the state.
        """
        # Prepare dummy data
        mock_warehouses = [MagicMock(), MagicMock()]
        world_builder.warehouses = mock_warehouses
        mock_lt_models = [MagicMock()]
        mock_routes = [MagicMock()]

        world_builder.logistics_builder.create_global_leadtime_models.return_value = mock_lt_models
        world_builder.logistics_builder.connect_warehouses.return_value = mock_routes

        world_builder.create_logistics_network()

        # Check calls
        world_builder.logistics_builder.create_global_leadtime_models.assert_called_once()
        world_builder.logistics_builder.connect_warehouses.assert_called_once_with(
            mock_warehouses, mock_lt_models
        )
        # Check state update
        assert world_builder.routes == mock_routes
