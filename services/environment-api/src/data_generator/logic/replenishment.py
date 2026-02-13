# file: services/environment-api/src/data_generator/logic/replenishment.py
"""
Replenishment Manager Module.

This module simulates the role of a Purchasing Manager or an automated
Inventory Management System (IMS). It periodically reviews stock levels against
defined safety thresholds and generates Purchase Orders (POs) to restock
inventory from external suppliers.
"""
import random
from datetime import datetime, timedelta
from typing import List

from sqlalchemy.orm import Session
from packages.common.common.logging import get_logger
from packages.database.src.models import (
    Warehouse, Product, InventoryBalance, Supplier,
    PurchaseOrder, POLine, Shipment, LocationType, LeadtimeModel
)
from packages.database.src.enums import (
    POStatus, ShipmentStatus, ShipmentDirection, LeadtimeScope
)
from src.config import settings

logger = get_logger(__name__)


class ReplenishmentManager:
    """
    Manages the procurement lifecycle: Stock Review -> Reorder Decision -> PO Generation.

    This class implements a stochastic (s, S) inventory policy:
    - s (Reorder Point): When stock falls below this level, trigger an order.
    - S (Order-Up-To Level): Order enough to bring stock back to this level.
    """

    def __init__(self, session: Session, suppliers: List[Supplier]):
        self.session = session
        self.suppliers = suppliers
        self.rng = random.Random(settings.simulation.random_seed)

        self.standard_lt_model = self.session.query(LeadtimeModel).filter_by(
            scope=LeadtimeScope.GLOBAL
        ).first()

    def review_stock_levels(self, date: datetime, warehouses: List[Warehouse],
                            products: List[Product]) -> None:
        """
        Main entry point: Reviews inventory positions and triggers replenishment.

        To simulate realistic workflow constraints, this method does not review
        every product every day. It samples a subset (10%) of the catalog to
        simulate a periodic review cycle.
        """
        products_to_review = self.rng.sample(
            products,
            k=max(1, int(len(products) * settings.replenishment.review_catalog_fraction))
        )
        pos_created = 0

        for wh in warehouses:
            dock_loc = next((loc for loc in wh.locations if loc.type == LocationType.DOCK), None)
            if not dock_loc:
                continue

            for product in products_to_review:
                if self._check_and_replenish_product(wh, dock_loc.id, product, date):
                    pos_created += 1

        if pos_created > 0:
            logger.info(
                "replenishment_run_completed",
                pos_created=pos_created,
                date=date.isoformat()
            )

    def _check_and_replenish_product(self, warehouse: Warehouse, location_id: str,
                                     product: Product, date: datetime) -> bool:
        """
        Evaluates the inventory position for a single product and executes a
        buy order if the policy criteria are met.
        """
        current_qty = self._get_current_stock_level(location_id, product.id)

        reorder_point = settings.replenishment.policy.reorder_point
        target_level = settings.replenishment.policy.target_level

        if current_qty < reorder_point:
            order_qty = target_level - current_qty
            self._execute_procurement(warehouse, product, order_qty, date)
            return True

        return False

    def _get_current_stock_level(self, location_id: str, product_id: str) -> float:
        """
        Queries the current On-Hand balance from the ledger.
        """
        balance = self.session.query(InventoryBalance).filter_by(
            location_id=location_id,
            product_id=product_id
        ).first()

        return balance.on_hand if balance else 0.0

    def _execute_procurement(self, warehouse: Warehouse, product: Product,
                             qty: float, date: datetime) -> None:
        """
        Orchestrator for the creation of all procurement records.

        Delegates to specialized methods to ensure the Purchase Order,
        Line Item, and Inbound Shipment are created correctly and linked.
        """
        supplier = self._select_supplier()

        po = self._create_purchase_order(warehouse, supplier, date)

        self._create_po_line(po, product, qty)

        self._create_inbound_shipment(po, warehouse, date)

    def _select_supplier(self) -> Supplier:
        """Selects a random supplier from the approved list."""
        return self.rng.choice(self.suppliers)

    def _create_purchase_order(self, warehouse: Warehouse, supplier: Supplier,
                               date: datetime) -> PurchaseOrder:
        """Creates the Purchase Order header record."""
        po = PurchaseOrder(
            supplier_id=supplier.id,
            destination_warehouse_id=warehouse.id,
            status=POStatus.SUBMITTED,
            created_at=date,
            leadtime_model_id=self.standard_lt_model.id if self.standard_lt_model else None
        )
        self.session.add(po)
        self.session.flush()
        return po

    def _create_po_line(self, po: PurchaseOrder, product: Product, qty: float) -> None:
        """Creates the specific line item for the product being ordered."""
        line = POLine(
            purchase_order_id=po.id,
            product_id=product.id,
            qty_ordered=qty,
            qty_received=0.0
        )
        self.session.add(line)

    def _create_inbound_shipment(self, po: PurchaseOrder, warehouse: Warehouse,
                                 date: datetime) -> None:
        """
        Creates the shipment record representing the vendor's promise to deliver.
        Calculates the expected arrival date based on stochastic lead times.
        """
        arrival_date = self._calculate_arrival_date(date)

        shipment = Shipment(
            purchase_order_id=po.id,
            destination_warehouse_id=warehouse.id,
            direction=ShipmentDirection.INBOUND,
            status=ShipmentStatus.IN_TRANSIT,
            shipped_at=date,
            arrived_at=arrival_date
        )
        self.session.add(shipment)

    def _calculate_arrival_date(self, current_date: datetime) -> datetime:
        """
        Simulates stochastic lead time variability.
        Returns the expected arrival date based on a Gaussian distribution.
        """
        lead_time_days = int(self.rng.gauss(
            settings.replenishment.lead_time.mean_days,
            settings.replenishment.lead_time.std_dev_days
        ))

        lead_time_days = max(
            settings.replenishment.lead_time.min_days,
            lead_time_days
        )

        return current_date + timedelta(days=lead_time_days)
