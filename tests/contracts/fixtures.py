"""
Static data fixtures representing the exact JSON structures the Consumer expects.

Why this is important: Using shared fixtures for both Consumer and Provider tests
ensures the expected contract perfectly aligns with the mock data the Provider
returns during verification, preventing false-positive failures.
"""

SUPPLIER_FIXTURE = {"id": "sup-123", "name": "Acme Corp", "region": "NA", "reliability": 0.95}

SUPPLIERS_LIST_RESULT = {"data": [SUPPLIER_FIXTURE], "message": "Success"}

INVENTORY_FIXTURE = {"warehouse_id": "wh-01", "sku": "sku-999", "quantity": 1500}

INVENTORY_RESULT = {"data": [INVENTORY_FIXTURE], "message": "Success"}

DELAY_SUMMARY_FIXTURE = {
    "route_id": "rt-55",
    "average_delay_hours": 4.5,
    "delayed_shipments_count": 12,
}

DELAY_SUMMARY_RESULT = {"data": [DELAY_SUMMARY_FIXTURE], "message": "Success"}

OBSERVATIONS_FIXTURE = {
    "sku": "sku-999",
    "system_balance": 1500,
    "observed_balance": 1495,
    "variance": -5,
}

OBSERVATIONS_RESULT = {"data": [OBSERVATIONS_FIXTURE], "message": "Success"}

AT_RISK_ORDER_FIXTURE = {"order_id": "ord-777", "risk_score": 0.88, "missing_skus": ["sku-999"]}

AT_RISK_ORDERS_RESULT = {"data": [AT_RISK_ORDER_FIXTURE], "message": "Success"}
