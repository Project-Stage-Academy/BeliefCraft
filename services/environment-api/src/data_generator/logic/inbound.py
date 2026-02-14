"""
Inbound Manager Module.

This module is responsible for the receiving side of warehouse operations.
It identifies shipments that have physically arrived at a facility and
orchestrates the process of "docking" them—updating the shipment status,
verifying the content against Purchase Orders, and triggering the inventory
ledger to record the stock increase.
"""

from datetime import datetime

from common.logging import get_logger
from sqlalchemy import and_, select
from sqlalchemy.orm import Session
from src.data_generator.logic.inventory import InventoryLedger, ReceiptCommand

from packages.database.src.enums import LocationType, ShipmentStatus
from packages.database.src.models import Location, PurchaseOrder, Shipment, Warehouse

logger = get_logger(__name__)


class InboundManager:
    """
    Manages the lifecycle of inbound shipments from 'In Transit' to 'Delivered'.

    This class encapsulates the business logic for receiving goods, including:
    1. Identifying arriving shipments based on simulation time.
    2. Validating shipment documentation (POs).
    3. Delegating physical stock updates to the InventoryLedger.
    4. Updating financial/tracking status on the Shipment and PO Lines.
    """

    def __init__(self, session: Session):
        """
        Args:
            session (Session): The active database session for transaction management.
        """
        self.session = session
        self.ledger = InventoryLedger(session)

    def process_daily_arrivals(self, date: datetime) -> None:
        """
        Scans for and processes all shipments scheduled to arrive by the given date.

        This is the main entry point for the simulation tick. It finds any
        shipment where 'arrived_at' is on or before the current simulation clock
        and the status is still 'IN_TRANSIT'.

        Args:
            date (datetime): The current simulation timestamp.
        """
        shipments = self._fetch_arriving_shipments(date)

        if not shipments:
            return

        logger.info("processing_shipments", count=len(shipments), date=date.isoformat())

        for shipment in shipments:
            self._process_single_shipment(shipment, date)

    def _fetch_arriving_shipments(self, date: datetime) -> list[Shipment]:
        """
        Queries the database for qualifying inbound shipments.
        """
        stmt = select(Shipment).where(
            and_(Shipment.status == ShipmentStatus.IN_TRANSIT, Shipment.arrived_at <= date)
        )
        return list(self.session.execute(stmt).scalars().all())

    def _validate_shipment_integrity(
        self, shipment: Shipment
    ) -> tuple[PurchaseOrder, Location] | None:
        """
        Validates shipment prerequisites.
        Returns (PurchaseOrder, DestinationDock) if valid, else None.
        """
        # 1. Check for source document (PO)
        po = shipment.purchase_order
        if not po:
            logger.warning("shipment_missing_po", shipment_id=str(shipment.id))
            return None

        # 2. Check for destination warehouse
        dest_warehouse = shipment.destination_warehouse
        if not dest_warehouse:
            logger.error("shipment_missing_destination", shipment_id=str(shipment.id))
            return None

        # 3. Check for receiving area (Dock)
        destination_dock = self._get_warehouse_dock(dest_warehouse)
        if not destination_dock:
            logger.error("warehouse_missing_dock", warehouse_id=str(dest_warehouse.id))
            return None

        return po, destination_dock

    def _process_single_shipment(self, shipment: Shipment, date: datetime) -> None:
        """
        Executes the receiving workflow for a specific shipment.

        Validates the existence of a linked Purchase Order and a valid Dock location
        at the destination warehouse. If valid, iterates through PO lines to
        record inventory receipts and closes the shipment.

        Args:
            shipment (Shipment): The shipment entity to process.
            date (datetime): The effective date of the receipt.
        """

        validation_result = self._validate_shipment_integrity(shipment)
        if not validation_result:
            return

        po, destination_dock = validation_result

        # Process receipt for each line item using the safe 'po' variable
        for line in po.lines:
            # Assumption: No partial shipments/loss yet; received equals ordered
            qty_received = line.qty_ordered

            command: ReceiptCommand = ReceiptCommand(
                location=destination_dock,
                product_id=line.product_id,
                qty=qty_received,
                date=date,
                ref_id=shipment.id,
            )

            self.ledger.record_receipt(command)

            # Update the Purchase Order Line to reflect the received quantity
            line.qty_received += qty_received

        # Finalize the shipment state
        shipment.status = ShipmentStatus.DELIVERED
        logger.debug("shipment_finalized", shipment_id=str(shipment.id))

    def _get_warehouse_dock(self, warehouse: Warehouse) -> Location | None:
        """
        Retrieves the designated 'DOCK' location for a given warehouse.
        Returns None if no such location exists.
        """

        return next((loc for loc in warehouse.locations if loc.type == LocationType.DOCK), None)
