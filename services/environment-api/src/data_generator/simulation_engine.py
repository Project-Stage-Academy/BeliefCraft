# file: services/environment-api/src/data_generator/simulation_engine.py
"""
Simulation Engine Module.

This module contains the central clock and orchestrator for the warehouse world.
It acts as the "Physics Engine" of the simulation, ensuring that time progresses
linearly and that events occur in a logically consistent order (e.g., you cannot
sell an item before it has arrived).
"""
from datetime import datetime
from typing import List
import random

from sqlalchemy.orm import Session

from packages.common.common import logging
from packages.database.src.logistics import Supplier
from packages.database.src.models import Warehouse, Product
from src.data_generator.logic.inbound import InboundManager
from src.data_generator.logic.outbound import OutboundManager
from src.data_generator.logic.replenishment import ReplenishmentManager
from src.data_generator.logic.sensors import SensorManager

logger = logging.get_logger(__name__)


class SimulationEngine:
    """
    The dynamic heart of the environment.

    Responsible for simulating the flow of time and orchestrating the interactions
    between different warehouse subsystems (Inbound, Outbound, Inventory, Sensors).

    It delegates specific business logic to specialized 'Manager' classes while
    maintaining the global state and synchronization of the simulation.
    """

    def __init__(self, session: Session, warehouses: List[Warehouse],
                 products: List[Product], suppliers: List[Supplier]):
        """
        Initialize the simulation environment.

        Args:
            session (Session): Active database session for persisting generated events.
            warehouses (List[Warehouse]): The physical facilities to simulate.
            products (List[Product]): The catalog of items that can be traded.
            suppliers (List[Supplier]): The external vendors available for replenishment.
        """
        self.session = session
        self.warehouses = warehouses
        self.products = products
        self.suppliers = suppliers

        # Seed the random number generator for reproducible simulations
        self.rng = random.Random(42)

        # Initialize specialized subsystems
        # 1. Inbound: Handles arriving trucks and receiving stock.
        self.inbound_manager = InboundManager(session)

        # 2. Outbound: Handles customer orders and shipping stock.
        self.outbound_manager = OutboundManager(session)

        # 3. Replenishment: Decides when to buy more stock from suppliers.
        self.replenishment_manager = ReplenishmentManager(session, self.suppliers)

        # 4. Sensors: Generates noisy observations of the final state.
        self.sensor_manager = SensorManager(session)

        logger.info(
            'simulation_engine_initialized',
            warehouses_count=len(warehouses),
            products_count=len(products)
        )

    def tick(self, current_date: datetime) -> None:
        """
        Advances the simulation by one discrete time step (typically 1 day).

        This method acts as the 'Game Loop'. It triggers each subsystem in a
        strict sequence to maintain causality and data integrity.

        Order of Operations:
        1. **Inbound Processing**:
           Shipments scheduled for today arrive first. This ensures stock is
           'Received' and available on the shelf before we try to sell it.
           (Inventory +)

        2. **Outbound Processing (Demand)**:
           Customers place orders. We attempt to fulfill them using the stock
           that was just received (or was already there).
           (Inventory -)

        3. **Replenishment Review**:
           The 'Manager' reviews the resulting stock levels after sales.
           If stock is low, new Purchase Orders are created for future delivery.
           (Future Inventory +)

        4. **Sensor Update**:
           IoT devices scan the warehouse *after* all physical movements
           (In/Out) are complete. This generates the 'Observation' records
           that the AI agent will use to estimate the state.

        Args:
            current_date (datetime): The specific date to simulate.
        """
        logger.debug('tick_started', date=current_date.isoformat())

        # Step 1: Receive Goods
        self.inbound_manager.process_daily_arrivals(current_date)

        # Step 2: Sell Goods
        self.outbound_manager.process_daily_demand(
            current_date,
            self.warehouses,
            self.products
        )

        # Step 3: Reorder Goods
        self.replenishment_manager.review_stock_levels(
            current_date,
            self.warehouses,
            self.products
        )

        # Step 4: Observe State
        self.sensor_manager.generate_daily_observations(
            current_date,
            self.warehouses,
        )

        # Persist all changes for this day
        self.session.flush()
