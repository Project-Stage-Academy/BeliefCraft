"""
Simulation Engine Module.
This module contains the central clock and orchestrator for the warehouse world.
It acts as the "Physics Engine" of the simulation, ensuring that time progresses
linearly and that events occur in a logically consistent order (e.g., you cannot
sell an item before it has arrived).
"""

import random
from datetime import datetime

from common import logging
from sqlalchemy.orm import Session
from src.config_load import settings
from src.data_generator.simulation_processes import (
    InboundProcessor,
    OutboundProcessor,
    ReplenishmentProcessor,
    SensorProcessor,
    SimulationContext,
    SimulationProcessor,
)

from packages.database.src.models import Product, Supplier, Warehouse

logger = logging.get_logger(__name__)


class SimulationEngine:
    """
    The dynamic heart of the environment.
    Refactored to use a pluggable pipeline of processors.
    """

    def __init__(
        self,
        session: Session,
        warehouses: list[Warehouse],
        products: list[Product],
        suppliers: list[Supplier],
        processors: list[SimulationProcessor] | None = None,
    ):
        self.session = session
        self.warehouses = warehouses
        self.products = products
        self.suppliers = suppliers
        self.rng = random.Random(settings.simulation.random_seed)  # noqa: S311

        if processors is None:
            self.processors = [
                InboundProcessor(session),
                OutboundProcessor(session),
                ReplenishmentProcessor(session, suppliers),
                SensorProcessor(session),
            ]
        else:
            self.processors = processors

        logger.info(
            "simulation_engine_initialized",
            warehouses_count=len(warehouses),
            pipeline_steps=len(self.processors),
        )

    def tick(self, current_date: datetime) -> None:
        """
        Advances the simulation by one discrete time step.
        Iterates through the registered processor pipeline.
        """
        logger.debug("tick_started", date=current_date.isoformat())

        context = SimulationContext(
            current_date=current_date,
            session=self.session,
            warehouses=self.warehouses,
            products=self.products,
            suppliers=self.suppliers,
        )

        for processor in self.processors:
            processor.execute(context)

        self.session.flush()
