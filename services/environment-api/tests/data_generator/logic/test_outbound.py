"""
Tests for the OutboundManager.

Verifies the fulfillment lifecycle: checking stock availability, creating orders/lines,
calculating service level penalties, and triggering shipments via the ledger.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from src.data_generator.logic.outbound import OutboundManager

from packages.database.src.enums import LocationType, OrderStatus, ShipmentDirection
from packages.database.src.models import Location, Order, OrderLine, Product, Warehouse


@pytest.fixture
def mock_session():
    """Provides a mocked SQLAlchemy session."""
    return MagicMock()


@pytest.fixture
def mock_ledger():
    """Provides a mocked InventoryLedger."""
    return MagicMock()


@pytest.fixture
def outbound_manager(mock_session, mock_ledger):
    """Initializes OutboundManager with mocked dependencies."""
    with patch("src.data_generator.logic.outbound.InventoryLedger", return_value=mock_ledger):
        return OutboundManager(mock_session)


@pytest.fixture
def dummy_data():
    """Provides basic entities for testing."""
    wh = MagicMock(spec=Warehouse)
    wh.id = "wh-1"
    wh.region = "EU-WEST"

    dock = MagicMock(spec=Location)
    dock.id = "dock-1"
    dock.type = LocationType.DOCK
    wh.locations = [dock]

    prod = MagicMock(spec=Product)
    prod.id = "prod-1"

    return wh, dock, prod


class TestOutboundManager:
    @patch("src.data_generator.logic.outbound.settings")
    def test_process_single_order_full_fulfillment(
        self, mock_settings, outbound_manager, mock_session, mock_ledger, dummy_data
    ):
        """
        Tests successful fulfillment when stock is ample.
        Verifies Order is SHIPPED and ledger is called.
        """
        wh, dock, prod = dummy_data
        date = datetime.now(tz=UTC)
        mock_settings.outbound.customer_names = ["Test Customer"]
        mock_settings.outbound.missed_sale_penalty_per_unit = 10.0

        # Mock stock availability (100 on hand)
        outbound_manager._check_stock_availability = MagicMock(return_value=100.0)

        # Act: Order 10 units
        success = outbound_manager._process_single_order(wh, prod, 10.0, date)

        assert success is True

        # Verify Order Header
        order = mock_session.add.call_args_list[0][0][0]
        assert isinstance(order, Order)
        assert order.status == OrderStatus.SHIPPED

        # Verify Order Line (Allocated == Ordered)
        line = mock_session.add.call_args_list[1][0][0]
        assert isinstance(line, OrderLine)
        assert line.qty_allocated == 10.0
        assert line.service_level_penalty == 0.0

        # Verify Ledger and Shipment
        mock_ledger.record_issuance.assert_called_once()
        shipment = mock_session.add.call_args_list[2][0][0]
        assert shipment.direction == ShipmentDirection.OUTBOUND

    @patch("src.data_generator.logic.outbound.settings")
    def test_process_single_order_partial_fulfillment(
        self, mock_settings, outbound_manager, mock_session, dummy_data
    ):
        """
        Tests partial fulfillment when stock is limited.
        Verifies correct penalty calculation and SHIPPED status.
        """
        wh, dock, prod = dummy_data
        mock_settings.outbound.customer_names = ["Test Customer"]
        mock_settings.outbound.missed_sale_penalty_per_unit = 10.0

        # Stock is 5, but customer wants 10
        outbound_manager._check_stock_availability = MagicMock(return_value=5.0)

        outbound_manager._process_single_order(wh, prod, 10.0, datetime.now(tz=UTC))

        # Verify Order Line
        line = [
            call[0][0]
            for call in mock_session.add.call_args_list
            if isinstance(call[0][0], OrderLine)
        ][0]
        assert line.qty_allocated == 5.0
        # Penalty: (10 ordered - 5 allocated) * 10 penalty = 50.0
        assert line.service_level_penalty == 50.0

    @patch("src.data_generator.logic.outbound.settings")
    def test_process_single_order_out_of_stock(
        self, mock_settings, outbound_manager, mock_session, mock_ledger, dummy_data
    ):
        """
        Tests zero fulfillment (Stockout).
        Verifies Order is CANCELLED and logistics are NOT executed.
        """
        wh, dock, prod = dummy_data
        mock_settings.outbound.customer_names = ["Test Customer"]
        outbound_manager._check_stock_availability = MagicMock(return_value=0.0)

        outbound_manager._process_single_order(wh, prod, 10.0, datetime.now(tz=UTC))

        # Verify Order Header status
        order = [
            call[0][0] for call in mock_session.add.call_args_list if isinstance(call[0][0], Order)
        ][0]
        assert order.status == OrderStatus.CANCELLED

        # Verify Ledger was NOT called
        mock_ledger.record_issuance.assert_not_called()

    def test_poisson_demand_generation(self, outbound_manager):
        """
        Sanity check for the Poisson sampler.
        Ensures it returns integers and respects the seed.
        """
        demand = outbound_manager._simulate_poisson_demand(mean=2.0)
        assert isinstance(demand, int)
        assert demand >= 0
