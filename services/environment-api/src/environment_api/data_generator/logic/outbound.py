"""
Outbound Manager Module.

Responsible for the 'Demand' side of the simulation. This module:
1. Generates stochastic customer demand using Poisson distributions.
2. Allocates available inventory to meet that demand (First-Come-First-Served).
3. Creates the necessary database records: Orders, OrderLines, and Shipments.
4. Triggers the InventoryLedger to physically deduct stock.
"""

import random
from datetime import datetime

import numpy as np
from common.logging import get_logger
from database.enums import LocationType, OrderStatus, ShipmentDirection, ShipmentStatus
from database.models import (
    InventoryBalance,
    Location,
    Order,
    OrderLine,
    Product,
    Shipment,
    Warehouse,
)
from environment_api.config_load import settings
from environment_api.data_generator.logic.inventory import InventoryLedger, ReceiptCommand
from sqlalchemy.orm import Session

logger = get_logger(__name__)


class OutboundManager:
    """
    Simulates the sales and fulfillment lifecycle.

    This class acts as a stochastic demand generator. Instead of reading from
    historical files, it generates 'synthetic history' by sampling probability
    distributions (Poisson) for every product, every day.
    """

    def __init__(self, session: Session):
        self.session = session
        self.ledger = InventoryLedger(session)
        self.rng = random.Random(settings.simulation.random_seed)  # noqa: S311

    def process_daily_demand(
        self, date: datetime, warehouses: list[Warehouse], products: list[Product]
    ) -> None:
        """
        Main entry point: Generates and attempts to fulfill random orders.

        To optimize performance and simulate realistic sales patterns, this method
        does not generate demand for every product every day. Instead, it samples
        a subset (20%) of the catalog to represent 'active' products for the day.

        Args:
            date (datetime): The current simulation date.
            warehouses (List[Warehouse]): List of active warehouses.
            products (List[Product]): Master product catalog.
        """
        orders_created = 0

        active_products = self.rng.sample(
            products, k=max(1, int(len(products) * settings.outbound.active_catalog_fraction))
        )

        for wh in warehouses:
            for product in active_products:
                qty_demanded = np.random.poisson(settings.outbound.poisson_mean)

                if qty_demanded <= 0:
                    continue

                if self._process_single_order(wh, product, qty_demanded, date):
                    orders_created += 1

        if orders_created > 0:
            logger.info(
                "daily_demand_processed", date=date.isoformat(), orders_created=orders_created
            )

    def _process_single_order(
        self, warehouse: Warehouse, product: Product, qty_ordered: float, date: datetime
    ) -> bool:
        """
        Orchestrates the fulfillment workflow for a single potential order.
        Returns True if an order was successfully created.
        """
        dock_location = self._get_dock(warehouse)
        if not dock_location:
            return False

        available_qty = self._check_stock_availability(dock_location, product)

        qty_to_ship = min(qty_ordered, available_qty)

        order = self._create_order_header(warehouse, qty_to_ship)

        self._create_order_line(order, product, qty_ordered, qty_to_ship)

        if qty_to_ship > 0:
            self._execute_outbound_logistics(
                warehouse=warehouse,
                dock=dock_location,
                product=product,
                order=order,
                qty=qty_to_ship,
                date=date,
            )

        return True

    def _check_stock_availability(self, location: Location, product: Product) -> float:
        """
        Queries the current On-Hand balance for a product at a location.
        """
        balance = (
            self.session.query(InventoryBalance)
            .filter_by(location_id=location.id, product_id=product.id)
            .first()
        )

        return balance.on_hand if balance else 0.0

    def _create_order_header(self, warehouse: Warehouse, allocated_qty: float) -> Order:
        """
        Creates the parent Order record.
        Status is determined by whether we could allocate ANY stock.
        """
        status = OrderStatus.SHIPPED if allocated_qty > 0 else OrderStatus.CANCELLED

        order = Order(
            customer_name=self.rng.choice(settings.outbound.customer_names),
            status=status,
            requested_ship_from_region=warehouse.region,
        )
        self.session.add(order)
        self.session.flush()
        return order

    def _create_order_line(
        self, order: Order, product: Product, ordered: float, allocated: float
    ) -> None:
        """
        Creates the OrderLine detail record.
        Calculates service level penalties for missed sales (Lost Sales).
        """
        line = OrderLine(
            order_id=order.id,
            product_id=product.id,
            qty_ordered=ordered,
            qty_allocated=allocated,
            qty_shipped=allocated,
            service_level_penalty=(ordered - allocated)
            * settings.outbound.missed_sale_penalty_per_unit,
        )
        self.session.add(line)

    def _execute_outbound_logistics(
        self,
        warehouse: Warehouse,
        dock: Location,
        product: Product,
        order: Order,
        qty: float,
        date: datetime,
    ) -> None:
        """
        Handles the physical movement of goods and shipment generation.
        Only called if stock was successfully allocated.
        """
        command: ReceiptCommand = ReceiptCommand(
            location=dock, product_id=product.id, qty=qty, date=date, ref_id=order.id
        )

        self.ledger.record_issuance(command)

        shipment = Shipment(
            order_id=order.id,
            origin_warehouse_id=warehouse.id,
            direction=ShipmentDirection.OUTBOUND,
            status=ShipmentStatus.IN_TRANSIT,
            shipped_at=date,
        )
        self.session.add(shipment)

    def _get_dock(self, warehouse: Warehouse) -> Location | None:
        """Retrieves the designated loading dock for the warehouse."""
        return next((loc for loc in warehouse.locations if loc.type == LocationType.DOCK), None)
