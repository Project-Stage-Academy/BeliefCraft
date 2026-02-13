"""
Inbound Manager Module.

This module is responsible for the receiving side of warehouse operations.
It identifies shipments that have physically arrived at a facility and
orchestrates the process of "docking" them—updating the shipment status,
verifying the content against Purchase Orders, and triggering the inventory
ledger to record the stock increase.
"""
from datetime import datetime
from typing import List, Optional
from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from common.logging import get_logger
from packages.database.src.models import Shipment, Location, Warehouse
from packages.database.src.enums import ShipmentStatus, LocationType
from src.data_generator.logic.inventory import InventoryLedger

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

        logger.info(
            "processing_shipments",
            count=len(shipments),
            date=date.isoformat()
        )

        for shipment in shipments:
            self._process_single_shipment(shipment, date)

    def _fetch_arriving_shipments(self, date: datetime) -> List[Shipment]:
        """
        Queries the database for qualifying inbound shipments.
        """
        stmt = select(Shipment).where(
            and_(
                Shipment.status == ShipmentStatus.IN_TRANSIT,
                Shipment.arrived_at <= date
            )
        )
        return list(self.session.execute(stmt).scalars().all())

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
        # Data integrity check: A shipment must have a source document (PO)
        if not shipment.purchase_order:
            logger.warning(
                "shipment_missing_po",
                shipment_id=str(shipment.id)
            )
            return

        # Data integrity check: Destination warehouse must have a receiving area (Dock)
        destination_dock = self._get_warehouse_dock(shipment.destination_warehouse)
        if not destination_dock:
            logger.error(
                "warehouse_missing_dock",
                warehouse_id=str(shipment.destination_warehouse_id)
            )
            return

        # Process receipt for each line item
        for line in shipment.purchase_order.lines:
            # Assumption: No partial shipments/loss yet; received equals ordered
            qty_received = line.qty_ordered

            self.ledger.record_receipt(
                location=destination_dock,
                product_id=line.product_id,
                qty=qty_received,
                date=date,
                ref_id=shipment.id
            )

            # Update the Purchase Order Line to reflect the received quantity
            line.qty_received += qty_received

        # Finalize the shipment state
        shipment.status = ShipmentStatus.DELIVERED
        logger.debug("shipment_finalized", shipment_id=str(shipment.id))

    def _get_warehouse_dock(self, warehouse: Warehouse) -> Optional[Location]:
        """
        Retrieves the designated 'DOCK' location for a given warehouse.
        Returns None if no such location exists.
        """

        return next(
            (loc for loc in warehouse.locations if loc.type == LocationType.DOCK),
            None
        )
