from __future__ import annotations

from environment_api.api.smart_query_routes import (
    device_monitoring_router,
    inventory_audit_router,
    legacy_router,
    observed_inventory_router,
    procurement_router,
    topology_router,
)
from environment_api.smart_query_builder.tools.inventory_tools import get_current_inventory
from environment_api.smart_query_builder.tools.observation_tools import (
    compare_observations_to_balances,
)
from environment_api.smart_query_builder.tools.order_tools import get_at_risk_orders
from environment_api.smart_query_builder.tools.shipment_tools import get_shipments_delay_summary
from fastapi import APIRouter

router = APIRouter(prefix="/smart-query", tags=["smart-query"])
router.include_router(inventory_audit_router)
router.include_router(observed_inventory_router)
router.include_router(device_monitoring_router)
router.include_router(procurement_router)
router.include_router(topology_router)
router.include_router(legacy_router)
