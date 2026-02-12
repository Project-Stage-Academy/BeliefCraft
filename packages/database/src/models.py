"""ORM compatibility module.

Keep this file as the stable import location for tests and downstream code,
while domain models live in separate modules.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_repo_root() -> None:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "packages").exists():
            if str(parent) not in sys.path:
                sys.path.insert(0, str(parent))
            return


try:
    from packages.database.src.base import Base
    from packages.database.src.enums import (
        DeviceStatus,
        DeviceType,
        DistFamily,
        LeadtimeScope,
        LocationType,
        MoveType,
        ObservationType,
        OrderStatus,
        POStatus,
        QualityStatus,
        ShipmentDirection,
        ShipmentStatus,
        TransportMode,
    )
    from packages.database.src.inventory import (
        InventoryBalance,
        InventoryMove,
        Location,
        Product,
    )
    from packages.database.src.logistics import (
        LeadtimeModel,
        Route,
        Shipment,
        Supplier,
        Warehouse,
    )
    from packages.database.src.observations import (
        Observation,
        SensorDevice,
    )
    from packages.database.src.orders import (
        Order,
        OrderLine,
        POLine,
        PurchaseOrder,
    )
except ModuleNotFoundError:
    _ensure_repo_root()
    from packages.database.src.base import Base
    from packages.database.src.enums import (
        DeviceStatus,
        DeviceType,
        DistFamily,
        LeadtimeScope,
        LocationType,
        MoveType,
        ObservationType,
        OrderStatus,
        POStatus,
        QualityStatus,
        ShipmentDirection,
        ShipmentStatus,
        TransportMode,
    )
    from packages.database.src.inventory import (
        InventoryBalance,
        InventoryMove,
        Location,
        Product,
    )
    from packages.database.src.logistics import (
        LeadtimeModel,
        Route,
        Shipment,
        Supplier,
        Warehouse,
    )
    from packages.database.src.observations import (
        Observation,
        SensorDevice,
    )
    from packages.database.src.orders import (
        Order,
        OrderLine,
        POLine,
        PurchaseOrder,
    )


__all__ = [
    "Base",
    "QualityStatus",
    "MoveType",
    "LocationType",
    "OrderStatus",
    "POStatus",
    "DeviceType",
    "DeviceStatus",
    "ShipmentStatus",
    "ShipmentDirection",
    "TransportMode",
    "LeadtimeScope",
    "DistFamily",
    "ObservationType",
    "Product",
    "Location",
    "InventoryBalance",
    "InventoryMove",
    "Order",
    "OrderLine",
    "PurchaseOrder",
    "POLine",
    "Warehouse",
    "Supplier",
    "LeadtimeModel",
    "Route",
    "Shipment",
    "SensorDevice",
    "Observation",
]
