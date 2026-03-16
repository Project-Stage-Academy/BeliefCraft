from __future__ import annotations

from environment_api.api.smart_query_routes import (
    device_monitoring_router,
    inventory_audit_router,
    observed_inventory_router,
    procurement_router,
    topology_router,
)
from fastapi import APIRouter

router = APIRouter(prefix="/smart-query", tags=["smart-query"])
router.include_router(inventory_audit_router)
router.include_router(observed_inventory_router)
router.include_router(device_monitoring_router)
router.include_router(procurement_router)
router.include_router(topology_router)
