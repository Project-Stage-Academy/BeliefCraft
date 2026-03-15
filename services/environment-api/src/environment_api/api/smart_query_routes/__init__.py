from .device_monitoring import router as device_monitoring_router
from .inventory_audit import router as inventory_audit_router
from .legacy import router as legacy_router
from .observed_inventory import router as observed_inventory_router
from .procurement import router as procurement_router
from .topology import router as topology_router

__all__ = [
    "device_monitoring_router",
    "inventory_audit_router",
    "legacy_router",
    "observed_inventory_router",
    "procurement_router",
    "topology_router",
]
