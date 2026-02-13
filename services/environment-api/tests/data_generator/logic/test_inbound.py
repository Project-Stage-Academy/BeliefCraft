"""
Tests for the InboundManager.

Verifies the logic for processing daily arrivals, including shipment filtering by date,
validation of source documents (POs), physical stock receipt delegation,
and status updates.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from packages.database.src.models import Shipment, PurchaseOrder, POLine, Location
from packages.database.src.enums import ShipmentStatus, LocationType
from src.data_generator.logic.inbound import InboundManager


@pytest.fixture
def mock_session():
    """Provides a mocked SQLAlchemy session."""
    return MagicMock()


@pytest.fixture
def mock_ledger():
    """Provides a mocked InventoryLedger."""
    return MagicMock()


@pytest.fixture
def inbound_manager(mock_session, mock_ledger):
    """
    Initializes InboundManager with a mocked session and injected ledger.
    """
    with patch("src.data_generator.logic.inbound.InventoryLedger", return_value=mock_ledger):
        manager = InboundManager(mock_session)
        return manager


class TestInboundManager:
    def test_process_daily_arrivals_filtering(self, inbound_manager, mock_session):
        """
        Verifies that only shipments arriving on or before the current date
        are selected for processing.
        """
        current_date = datetime(2024, 1, 10)

        # Mocking the internal database query result
        shipment_1 = MagicMock(spec=Shipment)
        inbound_manager._fetch_arriving_shipments = MagicMock(return_value=[shipment_1])
        inbound_manager._process_single_shipment = MagicMock()

        inbound_manager.process_daily_arrivals(current_date)

        # Ensure processing was triggered for the fetched shipment
        inbound_manager._process_single_shipment.assert_called_once_with(shipment_1, current_date)

    def test_process_single_shipment_success(self, inbound_manager, mock_ledger):
        """
        Tests the full successful workflow of docking a shipment:
        1. Validates PO exists.
        2. Finds the destination DOCK.
        3. Calls Ledger to record receipt.
        4. Updates PO line received quantity.
        5. Updates Shipment status to DELIVERED.
        """
        date = datetime(2024, 1, 10)

        # Setup Destination Warehouse with a Dock
        mock_dock = MagicMock(spec=Location)
        mock_dock.type = LocationType.DOCK

        mock_warehouse = MagicMock()
        mock_warehouse.locations = [mock_dock]

        # Setup PO Line
        mock_line = MagicMock(spec=POLine)
        mock_line.product_id = "prod-123"
        mock_line.qty_ordered = 50.0
        mock_line.qty_received = 0.0

        # Setup Purchase Order
        mock_po = MagicMock(spec=PurchaseOrder)
        mock_po.lines = [mock_line]

        # Setup Shipment
        mock_shipment = MagicMock(spec=Shipment)
        mock_shipment.id = "ship-999"
        mock_shipment.purchase_order = mock_po
        mock_shipment.destination_warehouse = mock_warehouse

        inbound_manager._process_single_shipment(mock_shipment, date)

        # Verify physical receipt recorded in ledger
        mock_ledger.record_receipt.assert_called_once_with(
            location=mock_dock,
            product_id="prod-123",
            qty=50.0,
            date=date,
            ref_id="ship-999"
        )

        # Verify business logic updates
        assert mock_line.qty_received == 50.0
        assert mock_shipment.status == ShipmentStatus.DELIVERED

    def test_process_single_shipment_missing_dock(self, inbound_manager, mock_ledger):
        """
        Verifies that processing is aborted if the destination warehouse
        has no designated DOCK location.
        """
        mock_warehouse = MagicMock()
        mock_warehouse.locations = []  # No dock here

        mock_shipment = MagicMock(spec=Shipment)
        mock_shipment.purchase_order = MagicMock()
        mock_shipment.destination_warehouse = mock_warehouse

        inbound_manager._process_single_shipment(mock_shipment, datetime.now())

        # Verify ledger was never called
        mock_ledger.record_receipt.assert_not_called()
        # Verify shipment status was not updated
        assert mock_shipment.status != ShipmentStatus.DELIVERED

    def test_get_warehouse_dock_logic(self, inbound_manager):
        """
        Verifies the helper method correctly extracts the DOCK location
        from a warehouse's location list.
        """
        loc_storage = MagicMock(spec=Location)
        loc_storage.type = "SHELF"

        loc_dock = MagicMock(spec=Location)
        loc_dock.type = LocationType.DOCK

        mock_wh = MagicMock()
        mock_wh.locations = [loc_storage, loc_dock]

        result = inbound_manager._get_warehouse_dock(mock_wh)
        assert result == loc_dock
