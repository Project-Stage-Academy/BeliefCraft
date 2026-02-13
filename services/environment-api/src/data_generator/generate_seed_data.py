"""
Database Seeding Script.

This script serves as the main entry point for generating synthetic data for the
environment-api service. It orchestrates the entire data generation lifecycle,
transforming an empty database into a rich, historical simulation of a logistics
network.

Phases:
    1. Database Reset: Drops and recreates all tables defined in Base.metadata.
    2. Static World Build: Uses WorldBuilder to create physical entities
       (Warehouses, Docks, Zones) and catalog entities (Products, Suppliers).
    3. Historical Simulation: Uses SimulationEngine to run a day-by-day
       simulation loop from (Today - N days) to Today. This generates:
       - Inbound Shipments (Receiving)
       - Outbound Orders (Demand)
       - Replenishment POs (Restocking)
       - Sensor Observations (IoT Data)

Key Classes:
    SimulationRunner: Encapsulates the execution logic and dependency injection.

Dependencies:
    - SQLAlchemy for database interactions.
    - WorldBuilder for static data.
    - SimulationEngine for dynamic event generation.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from packages.database.src.connection import SessionLocal, get_engine
from packages.database.src.base import Base
from packages.common.common.logging import configure_logging, get_logger

from src.data_generator.world_builder import WorldBuilder
from src.data_generator.simulation_engine import SimulationEngine
from src.config_load import settings

configure_logging("seed-generator", "INFO")
logger = get_logger(__name__)


class SimulationRunner:
    """
    Orchestrates the end-to-end data generation process.

    Responsibilities:
    1. Database Lifecycle Management (Reset/Init).
    2. Phase 1 Execution: Static World Construction.
    3. Phase 2 Execution: Time-Series Simulation.
    """

    def __init__(self, engine: Engine):
        self.engine = engine

    def run(self, days: int) -> None:
        """
        Main entry point. Executes the simulation pipeline.
        """
        self._reset_database()

        session = SessionLocal(bind=self.engine)
        try:
            # Phase 1: Create the physical world
            world = self._build_static_world(session)

            # Phase 2: Run the clock
            self._simulate_history(session, world, days)

            logger.info("seed_generation_success", total_days=days)

        except Exception as e:
            session.rollback()
            logger.error("seed_generation_failed", error=str(e), exc_info=True)
            raise
        finally:
            session.close()

    def _reset_database(self) -> None:
        """
        Drops and recreates all tables to ensure a clean slate.
        """
        logger.warning("database_reset_started")
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        logger.warning("database_reset_completed")

    def _build_static_world(self, session: Session) -> WorldBuilder:
        """
        Phase 1: Generates static entities (Warehouses, Products, Routes).
        """
        logger.info("phase_1_static_build_started")

        world = WorldBuilder(session, seed=settings.simulation.random_seed)
        world.build_all()

        session.commit()
        logger.info("phase_1_static_build_completed")
        return world

    def _simulate_history(self, session: Session, world: WorldBuilder, days: int) -> None:
        """
        Phase 2: Runs the Simulation Engine loop to generate historical events.
        """
        end_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        start_date = end_date - timedelta(days=days)

        logger.info(
            "phase_2_simulation_started",
            days=days,
            start=start_date.isoformat()
        )

        sim_engine = SimulationEngine(
            session=session,
            warehouses=world.warehouses,
            products=world.products,
            suppliers=world.suppliers
        )

        self._run_time_loop(session, sim_engine, start_date, end_date)

    def _run_time_loop(self, session: Session, engine: SimulationEngine,
                       start: datetime, end: datetime) -> None:
        """
        Iterates through every day in the simulation window.
        """
        current_date = start
        total_ticks = 0
        total_days = (end - start).days

        while current_date <= end:
            engine.tick(current_date)

            if total_ticks % settings.simulation.commit_interval == 0:
                session.commit()
                logger.info("simulation_progress", progress=f"{total_ticks}/{total_days}")

            current_date += timedelta(days=1)
            total_ticks += 1

        session.commit()

if __name__ == "__main__":
    engine = get_engine()
    runner = SimulationRunner(engine)
    runner.run(days=settings.simulation.default_days)
