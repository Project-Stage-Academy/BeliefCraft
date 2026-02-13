"""
Tests for the LogisticsBuilder.

Validates the creation of global LeadtimeModels and the generation of a
fully connected mesh network (Routes) between warehouses with distance-based
transport mode selection.
"""

import pytest
from unittest.mock import MagicMock, patch

from packages.database.src.models import Warehouse, Route, LeadtimeModel
from packages.database.src.enums import TransportMode, LeadtimeScope
from src.data_generator.builders.logistics import LogisticsBuilder


@pytest.fixture
def mock_session():
    """Provides a mocked SQLAlchemy session."""
    return MagicMock()


@pytest.fixture
def dummy_warehouses():
    """Provides a list of 3 dummy warehouses to test mesh connectivity."""
    whs = []
    for i in range(3):
        wh = Warehouse(name=f"WH-{i}", region="NA", tz="UTC")
        wh.id = f"uuid-{i}"
        whs.append(wh)
    return whs


@pytest.fixture
def dummy_models():
    """Provides a list of 3 dummy LeadtimeModels [Express, Standard, Ocean]."""
    models = []
    for i in range(3):
        model = LeadtimeModel(scope=LeadtimeScope.GLOBAL)
        model.id = i + 100  # Dummy IDs
        models.append(model)
    return models


class TestLogisticsBuilder:
    def test_create_global_leadtime_models(self, mock_session):
        """
        Verifies that three distinct global leadtime models are created
        and added to the database session.
        """
        builder = LogisticsBuilder(mock_session)
        models = builder.create_global_leadtime_models()

        assert len(models) == 3
        mock_session.add_all.assert_called_once_with(models)
        mock_session.flush.assert_called_once()

    def test_connect_warehouses_mesh_logic(self, mock_session, dummy_warehouses, dummy_models):
        """
        Verifies that a fully connected mesh network is created.
        For 3 warehouses, there should be n*(n-1) = 6 routes.
        """
        builder = LogisticsBuilder(mock_session)
        routes = builder.connect_warehouses(dummy_warehouses, dummy_models)

        # 3 warehouses -> (WH0->WH1, WH0->WH2, WH1->WH0, WH1->WH2, WH2->WH0, WH2->WH1)
        assert len(routes) == 6
        assert mock_session.add.call_count == 6

    @patch("src.data_generator.builders.logistics.settings")
    @patch("src.data_generator.builders.logistics.random.randint")
    def test_transport_mode_selection_logic(self, mock_randint, mock_settings,
                                            mock_session, dummy_warehouses, dummy_models):
        """
        Verifies that the correct transport mode and leadtime model are
        selected based on the generated distance tiers.
        """
        # Configure thresholds
        mock_settings.logistics.thresholds.truck_max_km = 800
        mock_settings.logistics.thresholds.air_max_km = 5000

        # Test 2 warehouses only for simplicity (2 routes: A->B and B->A)
        whs = dummy_warehouses[:2]
        builder = LogisticsBuilder(mock_session)

        # Force distances: 500 (Truck), 2000 (Air), 6000 (Sea)
        # For 2 warehouses, loop runs twice, we need 2 distance values
        mock_randint.side_effect = [500, 6000]

        routes = builder.connect_warehouses(whs, dummy_models)

        # First Route (500km)
        assert routes[0].distance_km == 500
        assert routes[0].mode == TransportMode.TRUCK
        assert routes[0].leadtime_model_id == dummy_models[1].id  # Standard Model

        # Second Route (6000km)
        assert routes[1].distance_km == 6000
        assert routes[1].mode == TransportMode.SEA
        assert routes[1].leadtime_model_id == dummy_models[2].id  # Ocean Model

    def test_connect_warehouses_empty_list(self, mock_session, dummy_models, dummy_warehouses):
        """
        Verifies that no routes are created if fewer than 2 warehouses are provided.
        """
        builder = LogisticsBuilder(mock_session)
        routes = builder.connect_warehouses([], dummy_models)
        assert len(routes) == 0

        routes = builder.connect_warehouses([dummy_warehouses[0]], dummy_models)
        assert len(routes) == 0
