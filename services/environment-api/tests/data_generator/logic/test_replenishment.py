"""
Tests for the ReplenishmentManager.

Verifies the (s, S) inventory policy logic, purchase order generation,
supplier selection, and the stochastic calculation of inbound lead times.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from packages.database.src.models import (
    Warehouse, Product, Location, Supplier,
    PurchaseOrder, POLine, Shipment, LeadtimeModel
)
from packages.database.src.enums import POStatus, ShipmentStatus, LocationType
from src.data_generator.logic.replenishment import ReplenishmentManager


@pytest.fixture
def mock_session():
    """Provides a mocked SQLAlchemy session."""
    return MagicMock()


@pytest.fixture
def dummy_supplier():
    """Provides a dummy supplier for selection logic."""
    supplier = MagicMock(spec=Supplier)
    supplier.id = "supplier-123"
    return supplier


@pytest.fixture
def replenishment_manager(mock_session, dummy_supplier):
    """Initializes ReplenishmentManager with mocked DB results for constructor."""
    # Mock the leadtime model query in __init__
    mock_model = MagicMock(spec=LeadtimeModel)
    mock_model.id = "lt-model-uuid"
    mock_session.query().filter_by().first.return_value = mock_model

    return ReplenishmentManager(mock_session, [dummy_supplier])


@pytest.fixture
def dummy_warehouse_with_dock():
    """Provides a warehouse with a dock location."""
    wh = MagicMock(spec=Warehouse)
    wh.id = "wh-uuid"
    dock = MagicMock(spec=Location)
    dock.id = "dock-uuid"
    dock.type = LocationType.DOCK
    wh.locations = [dock]
    return wh, dock


class TestReplenishmentManager:
    @patch("src.data_generator.logic.replenishment.settings")
    def test_check_and_replenish_triggers_correctly(self, mock_settings, replenishment_manager,
                                                    mock_session, dummy_warehouse_with_dock):
        """
        Verifies that an order is triggered when stock is below reorder point.
        Calculation: order_qty = target_level - current_qty
        """
        wh, dock = dummy_warehouse_with_dock
        prod = MagicMock(spec=Product)
        prod.id = "prod-uuid"
        date = datetime.now(tz=timezone.utc)

        # Config: s=20, S=100
        mock_settings.replenishment.policy.reorder_point = 20.0
        mock_settings.replenishment.policy.target_level = 100.0

        # Case: Stock is 15 (Below 20) -> Should trigger order for 85
        replenishment_manager._get_current_stock_level = MagicMock(return_value=15.0)
        replenishment_manager._execute_procurement = MagicMock()

        triggered = replenishment_manager._check_and_replenish_product(wh, dock.id, prod, date)

        assert triggered is True
        replenishment_manager._execute_procurement.assert_called_once_with(wh, prod, 85.0, date)

    @patch("src.data_generator.logic.replenishment.settings")
    def test_check_and_replenish_skips_when_stocked(self, mock_settings, replenishment_manager,
                                                    dummy_warehouse_with_dock):
        """
        Verifies that no order is created if stock is above the reorder point.
        """
        wh, dock = dummy_warehouse_with_dock
        mock_settings.replenishment.policy.reorder_point = 20.0

        # Case: Stock is 25 (Above 20)
        replenishment_manager._get_current_stock_level = MagicMock(return_value=25.0)
        replenishment_manager._execute_procurement = MagicMock()

        triggered = replenishment_manager._check_and_replenish_product(wh, dock.id, MagicMock(), datetime.now(tz=timezone.utc))

        assert triggered is False
        replenishment_manager._execute_procurement.assert_not_called()

    def test_execute_procurement_orchestration(self, replenishment_manager, mock_session,
                                               dummy_warehouse_with_dock):
        """
        Verifies that execute_procurement creates the full chain of objects:
        PO -> PO Line -> Inbound Shipment.
        """
        wh, _ = dummy_warehouse_with_dock
        prod = MagicMock(spec=Product)
        prod.id = "prod-uuid"
        qty = 50.0
        date = datetime.now(tz=timezone.utc)

        replenishment_manager._execute_procurement(wh, prod, qty, date)

        # 3 entities should be added to the session
        # Use a list comprehension to check types because order might vary based on implementation
        added_objects = [call[0][0] for call in mock_session.add.call_args_list]

        assert any(isinstance(obj, PurchaseOrder) for obj in added_objects)
        assert any(isinstance(obj, POLine) for obj in added_objects)
        assert any(isinstance(obj, Shipment) for obj in added_objects)

        # Verify Shipment details
        shipment = next(obj for obj in added_objects if isinstance(obj, Shipment))
        assert shipment.status == ShipmentStatus.IN_TRANSIT
        assert shipment.arrived_at > date  # Lead time should be positive

    @patch("src.data_generator.logic.replenishment.settings")
    def test_calculate_arrival_date_min_bounds(self, mock_settings, replenishment_manager):
        """
        Ensures that even with extreme Gaussian noise, arrival date
        respects the min_days configuration.
        """
        date = datetime(2024, 1, 1, tzinfo=timezone.utc)
        mock_settings.replenishment.lead_time.mean_days = 5.0
        mock_settings.replenishment.lead_time.std_dev_days = 1.0
        mock_settings.replenishment.lead_time.min_days = 2

        # Force a very negative random number from Gauss
        replenishment_manager.rng.gauss = MagicMock(return_value=-100.0)

        arrival = replenishment_manager._calculate_arrival_date(date)

        # Should be date + 2 days (min_days)
        assert arrival == date + timedelta(days=2)
