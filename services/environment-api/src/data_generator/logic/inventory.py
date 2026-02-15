"""
Inventory Ledger Module.

This module acts as the authoritative record-keeper for all physical inventory
changes. It isolates the database mechanics of updating balances and creating
audit trails (InventoryMoves) from the business logic of *why* those changes
occurred (e.g., Shipments, Orders, Adjustments).

This separation ensures that the simulation engine can simulate various
scenarios (theft, spoilage, sales) using a consistent accounting interface.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from packages.database.src.enums import MoveType, QualityStatus
from packages.database.src.models import InventoryBalance, InventoryMove, Location


@dataclass
class ReceiptCommand:
    """
    location (Location): The physical location (e.g., DOCK) receiving goods.
    product_id (uuid.UUID): The unique identifier of the product.
    qty (float): The quantity received. Must be positive.
    date (datetime): The simulation timestamp of the receipt.
    ref_id (uuid.UUID): The ID of the source document (e.g., Shipment ID).
    """

    location: Location
    product_id: uuid.UUID
    qty: float
    date: datetime
    ref_id: uuid.UUID


class InventoryLedger:
    """
    Manages the lifecycle of InventoryBalance records and ensures all stock
    changes are accompanied by an immutable InventoryMove audit log.

    This class serves as the 'Accountant' of the warehouse simulation:
    it does not make decisions, it only records transactions.
    """

    def __init__(self, session: Session):
        """
        Args:
            session (Session): The active database session for persistence.
        """
        self.session = session

    def record_receipt(self, command: ReceiptCommand) -> None:
        """
        Processes an inbound stock increase.

        This method is typically called by the InboundManager when a shipment
        is physically received at a dock. It updates the on-hand quantity
        and logs the event as an INBOUND move.

        """
        self._update_balance(command.location, command.product_id, command.qty)

        self._log_movement(
            command=command,
            move_type=MoveType.INBOUND,
            reason="PO_RECEIPT",
        )

    def record_issuance(self, command: ReceiptCommand) -> None:
        """
        Processes an outbound stock decrease (Shipment/Sale).

        Decrements the on-hand quantity and logs the movement.
        """

        self._update_balance(command.location, command.product_id, -command.qty)

        self._log_movement(
            command=command,
            move_type=MoveType.OUTBOUND,
            reason="CUSTOMER_ORDER",
        )

    def _update_balance(self, location: Location, product_id: uuid.UUID, qty: float) -> None:
        """
        Updates the perpetual inventory balance for a product at a specific location.

        If a balance record does not exist (e.g., new product in this warehouse),
        it initializes a new record with the starting quantity.
        """
        balance = (
            self.session.query(InventoryBalance)
            .filter_by(product_id=product_id, location_id=location.id)
            .first()
        )

        if balance:
            balance.on_hand += qty
        else:
            balance = InventoryBalance(
                product_id=product_id,
                location_id=location.id,
                on_hand=qty,
                reserved=0,
                quality_status=QualityStatus.OK,
            )
            self.session.add(balance)

    def _log_movement(self, command: ReceiptCommand, move_type: MoveType, reason: str) -> None:
        """
        Persists an immutable audit record of the inventory change.
        """
        move = InventoryMove(
            product_id=command.product_id,
            to_location_id=command.location.id,
            move_type=move_type,
            qty=command.qty,
            occurred_at=command.date,
            reason_code=reason,
        )
        self.session.add(move)
