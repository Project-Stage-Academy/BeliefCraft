"""
Layout Builders Module.

This module contains specialized builder classes responsible for generating
the physical and logical layout of a warehouse. It separates the construction
of shipping/receiving areas (Docks) from storage areas (Zones/Aisles).

Classes:
    DockBuilder: Handles creation of entry/exit points.
    ZoneBuilder: Handles creation of the internal storage hierarchy and sensor assets.
"""

from sqlalchemy.orm import Session

import random
from typing import List

from packages.database.src.models import (
    Warehouse, Location, LocationType,
    SensorDevice, DeviceType, DeviceStatus
)
from src.config import settings


class DockBuilder:
    """
    Specialist builder for shipping and receiving infrastructure.
    """

    def __init__(self, session: Session):
        """
        Args:
            session (Session): The active SQLAlchemy database session.
        """
        self.session = session

    def build(self, warehouse: Warehouse) -> Location:
        """
        Creates a single 'DOCK' location for the given warehouse.

        The Dock is a high-capacity location used as the staging area for
        inbound shipments (receiving) and outbound orders (shipping).

        Args:
            warehouse (Warehouse): The parent warehouse entity.

        Returns:
            Location: The created Dock location entity.
        """
        dock = Location(
            warehouse_id=warehouse.id,
            code=f"{warehouse.name}-DOCK",
            type=LocationType.DOCK,

            capacity_units=random.randint(
                settings.layout.dock.capacity_min,
                settings.layout.dock.capacity_max
            ) # nosec B311 - non-crypto random for simulation
        )
        self.session.add(dock)
        return dock


class ZoneBuilder:
    """
    Specialist builder for the internal storage hierarchy and IoT assets.
    Responsible for creating Zones, Aisles (Shelves), and generating Sensors.
    """

    def __init__(self, session: Session):
        """
        Args:
            session (Session): The active SQLAlchemy database session.
        """
        self.session = session

    def build_zones(self, warehouse: Warehouse) -> List[Location]:
        """
        Generates a randomized layout of storage zones for the warehouse.

        Creates virtual 'ZONE' locations (e.g., ZONE-A, ZONE-B).
        Each zone acts as a parent container for physical aisles.

        Args:
            warehouse (Warehouse): The parent warehouse entity.

        Returns:
            List[Location]: A list of created Zone location entities.
        """
        created_zones = []
        zone_count = random.randint(2, 5) # nosec B311 - non-crypto random for simulation

        zone_letters = [chr(65 + i) for i in range(zone_count)]

        for letter in zone_letters:
            zone_name = f"ZONE-{letter}"

            zone = Location(
                warehouse_id=warehouse.id,
                code=f"{warehouse.name}-{zone_name}",
                type=LocationType.VIRTUAL,
                capacity_units=random.randint(
                    settings.layout.zone.capacity_min,
                    settings.layout.zone.capacity_max
                ) # nosec B311 - non-crypto random for simulation
            )
            self.session.add(zone)
            self.session.flush()

            self._build_aisles(warehouse, zone, zone_name)
            created_zones.append(zone)

        return created_zones

    def _build_aisles(self, warehouse: Warehouse, zone: Location, zone_name: str) -> None:
        """
        Helper method to create physical shelves (Aisles) within a specific zone.

        Creates 'SHELF' locations per zone. Also triggers the probability
        check to add a sensor for each created aisle.

        Args:
            warehouse (Warehouse): The parent warehouse (for sensor linking).
            zone (Location): The parent zone location.
            zone_name (str): The code prefix for the zone (e.g., "ZONE-A").
        """
        aisle_count = random.randint(
            settings.layout.aisle.count_min,
            settings.layout.aisle.count_max
        ) # nosec B311 - non-crypto random for simulation
        for aisle_num in range(1, aisle_count + 1):
            aisle = Location(
                warehouse_id=warehouse.id,
                parent_location_id=zone.id,
                code=f"{zone_name}-AISLE-{aisle_num:02d}",
                type=LocationType.SHELF,
                capacity_units=random.randint(
                    settings.layout.aisle.capacity_min,
                    settings.layout.aisle.capacity_max
                ) # nosec B311 - non-crypto random for simulation
            )
            self.session.add(aisle)
            self.session.flush()

            self._attach_sensor(warehouse)

    def _attach_sensor(self, warehouse: Warehouse) -> None:
        """
        Probabilistically adds a sensor device to the warehouse inventory.

        There is an 80% chance this method does nothing (no sensor).
        If a sensor is created, it is linked to the Warehouse ID (not the specific aisle).

        Args:
            warehouse (Warehouse): The warehouse that owns the device.
        """

        if random.random() > settings.layout.sensor.attach_probability:
            return

        device_type = random.choices(
            [DeviceType.CAMERA, DeviceType.RFID_READER],
            weights=[
                settings.layout.sensor.camera.weight,
                settings.layout.sensor.rfid.weight
            ],
            k=1
        )[0] # nosec B311 - non-crypto random for simulation

        if device_type == DeviceType.CAMERA:
            noise = random.uniform(
                settings.layout.sensor.camera.noise_min,
                settings.layout.sensor.camera.noise_max
            ) # nosec B311 - non-crypto random for simulation
            missing = random.uniform(
                settings.layout.sensor.camera.missing_min,
                settings.layout.sensor.camera.missing_max
            ) # nosec B311 - non-crypto random for simulation
        else:
            noise = random.uniform(
                settings.layout.sensor.rfid.noise_min,
                settings.layout.sensor.rfid.noise_max
            ) # nosec B311 - non-crypto random for simulation
            missing = random.uniform(
                settings.layout.sensor.rfid.missing_min,
                settings.layout.sensor.rfid.missing_max
            ) # nosec B311 - non-crypto random for simulation

        device = SensorDevice(
            warehouse_id=warehouse.id,
            device_type=device_type,
            status=DeviceStatus.ACTIVE,
            noise_sigma=noise,
            missing_rate=missing
        )
        self.session.add(device)
