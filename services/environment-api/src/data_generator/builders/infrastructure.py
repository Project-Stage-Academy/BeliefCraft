"""
This module provides the infrastructure orchestration logic for warehouse setup.
It handles the creation of Warehouse entities and delegates the construction
of internal layouts (Docks and Zones) to specialized builder components.
"""

from typing import List
from sqlalchemy.orm import Session
from packages.database.src.models import Warehouse
from src.config import settings
from .layout import DockBuilder, ZoneBuilder

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

    def create_warehouses(self, count) -> List[Warehouse]:
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
        region_tz_pairs = list(settings.infrastructure.region_timezones.items())

        for i in range(count):
            idx = i % len(region_tz_pairs)
            region, tz = region_tz_pairs[idx]

            wh = Warehouse(
                name=f"WH-{region}-{i + 1:02d}",
                region=region,
                tz=tz
            )
            self.session.add(wh)
            self.session.flush()

            # Delegate internal layout construction
            self.dock_builder.build(wh)
            self.zone_builder.build_zones(wh)

            created_warehouses.append(wh)

        return created_warehouses
