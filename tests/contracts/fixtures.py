"""
Static data fixtures representing the exact JSON structures.
Wrapped with `make_result` to mirror the Pydantic `ToolResult` model dump.
"""


def make_result(data: dict | list) -> dict:
    return {
        "data": data,
        "message": "Success",
        "meta": {},
    }


SUPPLIER_FIXTURE = {"id": "sup-123", "name": "Acme Corp", "region": "NA", "reliability_score": 0.95}
SUPPLIERS_LIST_RESULT = make_result({"suppliers": [SUPPLIER_FIXTURE]})
SUPPLIER_GET_RESULT = make_result({"supplier": SUPPLIER_FIXTURE})

PURCHASE_ORDER_FIXTURE = {
    "id": "po-123",
    "supplier_id": "sup-123",
    "destination_warehouse_id": "wh-01",
    "status": "submitted",
    "expected_at": "2023-10-15T00:00:00",
    "leadtime_model_id": "lt-1",
    "created_at": "2023-10-01T00:00:00",
    "supplier_name": "Acme Corp",
    "warehouse_name": "Central Hub",
}
PURCHASE_ORDERS_LIST_RESULT = make_result({"purchase_orders": [PURCHASE_ORDER_FIXTURE]})
PURCHASE_ORDER_GET_RESULT = make_result({"purchase_order": PURCHASE_ORDER_FIXTURE})

PO_LINE_FIXTURE = {
    "id": "line-1",
    "purchase_order_id": "po-123",
    "product_id": "prod-1",
    "qty_ordered": 100.0,
    "qty_received": 20.0,
    "remaining_qty": 80.0,
    "sku": "sku-999",
    "product_name": "Gadget",
    "category": "Electronics",
}
PO_LINES_LIST_RESULT = make_result({"po_lines": [PO_LINE_FIXTURE]})

PIPELINE_SUMMARY_FIXTURE = {
    "destination_warehouse_id": "wh-01",
    "supplier_id": "sup-123",
    "po_count": 5,
    "total_qty_ordered": 500.0,
    "total_qty_received": 100.0,
    "total_qty_remaining": 400.0,
    "next_expected_at": "2023-10-15T00:00:00",
    "last_created_at": "2023-10-01T00:00:00",
    "supplier_name": "Acme Corp",
    "warehouse_name": "Central Hub",
}
PIPELINE_SUMMARY_RESULT = make_result({"rows": [PIPELINE_SUMMARY_FIXTURE]})

INVENTORY_FIXTURE = {
    "warehouse_id": "wh-01",
    "location_id": "loc-1",
    "location_code": "A1",
    "product_id": "prod-1",
    "sku": "sku-999",
    "on_hand": 1500.0,
    "reserved": 0.0,
    "available": 1500.0,
    "quality_status": "good",
    "last_count_at": "2023-10-01T00:00:00",
}
INVENTORY_RESULT = make_result([INVENTORY_FIXTURE])

DELAY_SUMMARY_FIXTURE = {
    "shipment_id": "ship-1",
    "status": "delayed",
    "route_id": "rt-55",
    "origin_warehouse_id": "wh-01",
    "destination_warehouse_id": "wh-02",
    "shipped_at": "2023-01-01T00:00:00",
    "arrived_at": None,
    "transit_hours": 50.0,
    "delayed_reason": "In transit over 48 hours",
}
DELAY_SUMMARY_RESULT = make_result(
    {
        "total_shipments": 1,
        "delivered_count": 0,
        "in_transit_count": 1,
        "delayed_count": 1,
        "avg_transit_hours": 50.0,
        "delayed_shipments": [DELAY_SUMMARY_FIXTURE],
    }
)

OBSERVATIONS_FIXTURE = {
    "warehouse_id": "wh-01",
    "location_id": "loc-1",
    "sku": "sku-999",
    "product_id": "prod-1",
    "observed_estimate": 1495.0,
    "on_hand": 1500.0,
    "reserved": 0.0,
    "available": 1500.0,
    "discrepancy": -5.0,
    "obs_count": 1,
    "avg_confidence": 0.9,
}
OBSERVATIONS_RESULT = make_result([OBSERVATIONS_FIXTURE])

AT_RISK_ORDER_FIXTURE = {
    "order_id": "ord-777",
    "status": "open",
    "promised_at": "2023-10-15T00:00:00",
    "sla_priority": 0.88,
    "total_lines": 2,
    "total_open_qty": 10.0,
    "total_penalty_exposure": 500.0,
    "top_missing_skus": ["sku-999"],
}
AT_RISK_ORDERS_RESULT = make_result([AT_RISK_ORDER_FIXTURE])
