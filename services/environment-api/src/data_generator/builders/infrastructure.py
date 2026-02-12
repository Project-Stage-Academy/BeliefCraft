# services/environment-api/src/data_generator/builders/infrastructure.py

from typing import List
from sqlalchemy.orm import Session
from packages.database.src.models import Warehouse
from packages.common.logging import get_logger

# Import the workers
from .layout import DockBuilder, ZoneBuilder

logger = get_logger(__name__)


class InfrastructureBuilder:
    """
    Manager: Coordinates the creation of physical infrastructure.
    """

    def __init__(self, session: Session):
        self.session = session

        self.dock_builder = DockBuilder(session)
        self.zone_builder = ZoneBuilder(session)

    def create_warehouses(self, count: int = 3) -> List[Warehouse]:
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

            self.dock_builder.build(wh)
            self.zone_builder.build_zones(wh)

            created_warehouses.append(wh)

        return created_warehouses
