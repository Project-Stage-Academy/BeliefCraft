"""ORM compatibility module.

Keep this file as the stable import location for tests and downstream code,
while domain models live in separate modules.
"""

from __future__ import annotations

from pathlib import Path
import sys


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
        QualityStatus,
        MoveType,
        LocationType,
        OrderStatus,
        POStatus,
        DeviceType,
        DeviceStatus,
        ShipmentStatus,
        ShipmentDirection,
        TransportMode,
        LeadtimeScope,
        DistFamily,
        ObservationType,
    )
    from packages.database.src.inventory import (
        Product,
        Location,
        InventoryBalance,
        InventoryMove,
    )
    from packages.database.src.orders import (
        Order,
        OrderLine,
        PurchaseOrder,
        POLine,
    )
    from packages.database.src.logistics import (
        Warehouse,
        Supplier,
        LeadtimeModel,
        Route,
        Shipment,
    )
    from packages.database.src.observations import (
        SensorDevice,
        Observation,
    )
except ModuleNotFoundError:
    _ensure_repo_root()
    from packages.database.src.base import Base
    from packages.database.src.enums import (
        QualityStatus,
        MoveType,
        LocationType,
        OrderStatus,
        POStatus,
        DeviceType,
        DeviceStatus,
        ShipmentStatus,
        ShipmentDirection,
        TransportMode,
        LeadtimeScope,
        DistFamily,
        ObservationType,
    )
    from packages.database.src.inventory import (
        Product,
        Location,
        InventoryBalance,
        InventoryMove,
    )
    from packages.database.src.orders import (
        Order,
        OrderLine,
        PurchaseOrder,
        POLine,
    )
    from packages.database.src.logistics import (
        Warehouse,
        Supplier,
        LeadtimeModel,
        Route,
        Shipment,
    )
    from packages.database.src.observations import (
        SensorDevice,
        Observation,
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
