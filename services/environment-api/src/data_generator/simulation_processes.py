from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session
from src.data_generator.logic.inbound import InboundManager
from src.data_generator.logic.outbound import OutboundManager
from src.data_generator.logic.replenishment import ReplenishmentManager
from src.data_generator.logic.sensors import SensorManager

from packages.database.src.models import Product, Supplier, Warehouse


@dataclass
class SimulationContext:
    """
    Encapsulates the state required by processors to execute a simulation step.
    Functions as a specific DTO for the strategy pattern.
    """

    current_date: datetime
    session: Session
    warehouses: list[Warehouse]
    products: list[Product]
    suppliers: list[Supplier]


class SimulationProcessor(ABC):
    """
    Strategy Interface: Defines the contract for any logic that wants to
    execute during a simulation tick.
    """

    @abstractmethod
    def execute(self, context: SimulationContext) -> None:
        pass


class InboundProcessor(SimulationProcessor):
    def __init__(self, session: Session):
        self.manager = InboundManager(session)

    def execute(self, context: SimulationContext) -> None:
        self.manager.process_daily_arrivals(context.current_date)


class OutboundProcessor(SimulationProcessor):
    def __init__(self, session: Session):
        self.manager = OutboundManager(session)

    def execute(self, context: SimulationContext) -> None:
        self.manager.process_daily_demand(
            context.current_date, context.warehouses, context.products
        )


class ReplenishmentProcessor(SimulationProcessor):
    def __init__(self, session: Session, suppliers: list[Supplier]):
        self.manager = ReplenishmentManager(session, suppliers)

    def execute(self, context: SimulationContext) -> None:
        self.manager.review_stock_levels(context.current_date, context.warehouses, context.products)


class SensorProcessor(SimulationProcessor):
    def __init__(self, session: Session):
        self.manager = SensorManager(session)

    def execute(self, context: SimulationContext) -> None:
        self.manager.generate_daily_observations(context.current_date, context.warehouses)
