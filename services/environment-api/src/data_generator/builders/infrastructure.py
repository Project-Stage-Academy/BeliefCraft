"""
This module provides the infrastructure orchestration logic for warehouse setup.
It handles the creation of Warehouse entities and delegates the construction
of internal layouts (Docks and Zones) to specialized builder components.
"""

from typing import List
from sqlalchemy.orm import Session
from packages.database.src.models import Warehouse
from packages.common.logging import get_logger

from .layout import DockBuilder, ZoneBuilder

logger = get_logger(__name__)


class InfrastructureBuilder:
    """
    Orchestrates the creation of warehouse infrastructure including associated
    docks and zones.

    This class serves as a facade for the underlying layout builders to ensure
    a consistent initialization of warehouse environments.
    """

    def __init__(self, session: Session):
        """
        Initializes the builder with a database session and internal layout builders.

        Args:
            session (Session): The SQLAlchemy session for database persistence.
        """
        self.session = session

        self.dock_builder = DockBuilder(session)
        self.zone_builder = ZoneBuilder(session)

    def create_warehouses(self, count: int = 3) -> List[Warehouse]:
        """
        Generates and persists a specified number of Warehouse records with
        pre-configured regions, timezones, and internal layouts.

        The method handles regional cycling and triggers DockBuilder and
        ZoneBuilder for each created warehouse instance.

        Args:
            count (int): The number of warehouse instances to generate. Defaults to 3.

        Returns:
            List[Warehouse]: A list of the successfully created Warehouse objects.
        """
        created_warehouses = []
        regions = ["NA-EAST", "EU-WEST", "APAC-SG", "NA-WEST", "EU-CENTRAL"]
        timezones = ["UTC-5", "UTC+1", "UTC+8", "UTC-8", "UTC+2"]

        logger.info("infra_builder_started", count=count)

        for i in range(count):
            idx = i % len(regions)
            wh = Warehouse(
                name=f"WH-{regions[idx]}-{i + 1:02d}",
                region=regions[idx],
                tz=timezones[idx]
            )
            self.session.add(wh)
            self.session.flush()

            # Delegate internal layout construction
            self.dock_builder.build(wh)
            self.zone_builder.build_zones(wh)

            created_warehouses.append(wh)

        return created_warehouses
