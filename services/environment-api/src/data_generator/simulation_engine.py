from datetime import datetime
from typing import List
import random

from sqlalchemy.orm import Session

from packages.common import logging
from packages.database.src.models import Warehouse, Product
from src.data_generator.logic.inbound import InboundManager

logger = logging.get_logger(__name__)


class SimulationEngine:
    """
    The dynamic heart of the environment.
    Responsible for simulating the flow of time and events (Verbs).
    """

    def __init__(self, session: Session, warehouses: List[Warehouse], products: List[Product]):
        self.session = session
        self.warehouses = warehouses
        self.products = products

        self.rng = random.Random(42)

        # Initialize the specialist manager
        self.inbound_manager = InboundManager(session)

        logger.info(
            'simulation_engine_initialized',
            warehouses_count=len(warehouses),
            products_count=len(products)
        )

    def tick(self, current_date: datetime) -> None:
        """
        Advances the simulation by one time step (typically 1 day).

        The order of operations is critical for causality:
        1. Shipments arrive (Inventory UP) -> Delegated to InboundManager
        2. Customers order (Inventory DOWN)
        3. Manager reviews stock (Decides to buy more)
        4. Sensors record the final state (Observation)
        """

        logger.debug('tick_started', date=current_date.isoformat())

        # 1. Process Inbound Shipments (Connected!)
        self.inbound_manager.process_daily_arrivals(current_date)

        # 2. Process Outbound Demand (Placeholders)
        self._generate_demand(current_date)
        self._restock_inventory(current_date)
        self._update_sensors(current_date)

        self.session.flush()

    def _generate_demand(self, date: datetime) -> None:
        """
        Logic: For each Product/Warehouse, sample a Poisson distribution.
        Action: Create Order, OrderLine, and InventoryMove (-Qty).
        Note: If insufficient stock, mark as 'Lost Sale' or 'Backorder'.
        """
        pass

    def _restock_inventory(self, date: datetime) -> None:
        """
        Logic: The 'Manager' (Inventory Policy).
        Check if InventoryBalance < ReorderPoint.
        Action: Create PurchaseOrder and new Shipment (Status='PLANNED').
        """
        pass

    def _update_sensors(self, date: datetime) -> None:
        """
        Logic: Iterate through all Sensors.
        Action: Read actual InventoryBalance, add Gaussian Noise, save as Observation.
        """
        pass
