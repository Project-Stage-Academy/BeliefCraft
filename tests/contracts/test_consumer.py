from pathlib import Path

import pytest
import requests
from pact import Pact

from .fixtures import (
    AT_RISK_ORDERS_RESULT,
    DELAY_SUMMARY_RESULT,
    INVENTORY_RESULT,
    OBSERVATIONS_RESULT,
    PIPELINE_SUMMARY_RESULT,
    PO_LINES_LIST_RESULT,
    PURCHASE_ORDER_GET_RESULT,
    PURCHASE_ORDERS_LIST_RESULT,
    SUPPLIER_GET_RESULT,
    SUPPLIERS_LIST_RESULT,
)


# CHANGED: scope="function" (the default) so every test gets a clean slate.
@pytest.fixture
def pact_mock_server():
    pact = Pact("AgentClient", "EnvironmentAPI")
    yield pact

    pact_dir = Path.cwd() / "pacts"
    pact_dir.mkdir(exist_ok=True)
    pact.write_file(str(pact_dir))


def test_list_suppliers_contract(pact_mock_server: Pact):
    (
        pact_mock_server.upon_receiving("Request to list suppliers")
        .given("Supplier list exists")
        .with_request("GET", "/api/v1/smart-query/procurement/suppliers")
        .with_query_parameter("limit", "100")
        .with_query_parameter("offset", "0")
        .will_respond_with(200)
        .with_body(SUPPLIERS_LIST_RESULT, "application/json")
    )

    with pact_mock_server.serve() as srv:
        res = requests.get(
            f"{srv.url}/api/v1/smart-query/procurement/suppliers",
            params={"limit": 100, "offset": 0},
            timeout=100,
        )
    assert res.status_code == 200


def test_get_supplier_contract(pact_mock_server: Pact):
    (
        pact_mock_server.upon_receiving("Request single supplier")
        .given("Supplier sup-123 exists")
        .with_request("GET", "/api/v1/smart-query/procurement/suppliers/sup-123")
        .will_respond_with(200)
        .with_body(SUPPLIER_GET_RESULT, "application/json")
    )

    with pact_mock_server.serve() as srv:
        res = requests.get(
            f"{srv.url}/api/v1/smart-query/procurement/suppliers/sup-123",
            timeout=100,
        )
    assert res.status_code == 200


def test_list_purchase_orders_contract(pact_mock_server: Pact):
    (
        pact_mock_server.upon_receiving("Request to list POs")
        .given("Purchase orders list exists")
        .with_request("GET", "/api/v1/smart-query/procurement/purchase-orders")
        .with_query_parameter("limit", "100")
        .with_query_parameter("offset", "0")
        .will_respond_with(200)
        .with_body(PURCHASE_ORDERS_LIST_RESULT, "application/json")
    )

    with pact_mock_server.serve() as srv:
        res = requests.get(
            f"{srv.url}/api/v1/smart-query/procurement/purchase-orders",
            params={"limit": 100, "offset": 0},
            timeout=100,
        )
    assert res.status_code == 200


def test_get_purchase_order_contract(pact_mock_server: Pact):
    (
        pact_mock_server.upon_receiving("Request single PO")
        .given("Purchase order po-123 exists")
        .with_request("GET", "/api/v1/smart-query/procurement/purchase-orders/po-123")
        .will_respond_with(200)
        .with_body(PURCHASE_ORDER_GET_RESULT, "application/json")
    )

    with pact_mock_server.serve() as srv:
        res = requests.get(
            f"{srv.url}/api/v1/smart-query/procurement/purchase-orders/po-123",
            timeout=100,
        )
    assert res.status_code == 200


def test_list_po_lines_contract(pact_mock_server: Pact):
    (
        pact_mock_server.upon_receiving("Request PO lines")
        .given("PO lines exist")
        .with_request("GET", "/api/v1/smart-query/procurement/po-lines")
        .with_query_parameter("purchase_order_id", "po-123")
        .will_respond_with(200)
        .with_body(PO_LINES_LIST_RESULT, "application/json")
    )

    with pact_mock_server.serve() as srv:
        res = requests.get(
            f"{srv.url}/api/v1/smart-query/procurement/po-lines",
            params={"purchase_order_id": "po-123"},
            timeout=100,
        )
    assert res.status_code == 200


def test_pipeline_summary_contract(pact_mock_server: Pact):
    (
        pact_mock_server.upon_receiving("Request pipeline summary")
        .given("Pipeline summary data exists")
        .with_request("GET", "/api/v1/smart-query/procurement/pipeline-summary")
        .with_query_parameter("group_by", "warehouse_supplier")
        .will_respond_with(200)
        .with_body(PIPELINE_SUMMARY_RESULT, "application/json")
    )

    with pact_mock_server.serve() as srv:
        res = requests.get(
            f"{srv.url}/api/v1/smart-query/procurement/pipeline-summary",
            params={"group_by": "warehouse_supplier"},
            timeout=100,
        )
    assert res.status_code == 200


def test_current_inventory_contract(pact_mock_server: Pact):
    (
        pact_mock_server.upon_receiving("Request current inventory")
        .given("Inventory data exists")
        .with_request("GET", "/api/v1/smart-query/inventory/current")
        .with_query_parameter("limit", "50")
        .with_query_parameter("offset", "0")
        .will_respond_with(200)
        .with_body(INVENTORY_RESULT, "application/json")
    )

    with pact_mock_server.serve() as srv:
        res = requests.get(
            f"{srv.url}/api/v1/smart-query/inventory/current",
            params={"limit": 50, "offset": 0},
            timeout=100,
        )
    assert res.status_code == 200


def test_shipments_delay_summary_contract(pact_mock_server: Pact):
    (
        pact_mock_server.upon_receiving("Request delay summary")
        .given("Delay summary data exists")
        .with_request("GET", "/api/v1/smart-query/shipments/delay-summary")
        .with_query_parameter("date_from", "2023-01-01T00:00:00")
        .with_query_parameter("date_to", "2023-01-31T23:59:59")
        .will_respond_with(200)
        .with_body(DELAY_SUMMARY_RESULT, "application/json")
    )

    with pact_mock_server.serve() as srv:
        res = requests.get(
            f"{srv.url}/api/v1/smart-query/shipments/delay-summary",
            params={"date_from": "2023-01-01T00:00:00", "date_to": "2023-01-31T23:59:59"},
            timeout=100,
        )
    assert res.status_code == 200


def test_compare_balances_contract(pact_mock_server: Pact):
    (
        pact_mock_server.upon_receiving("Request balance comparison")
        .given("Balance comparison data exists")
        .with_request("GET", "/api/v1/smart-query/observations/compare-balances")
        .with_query_parameter("observed_from", "2023-01-01T00:00:00")
        .with_query_parameter("observed_to", "2023-01-31T23:59:59")
        .with_query_parameter("limit", "50")
        .with_query_parameter("offset", "0")
        .will_respond_with(200)
        .with_body(OBSERVATIONS_RESULT, "application/json")
    )

    with pact_mock_server.serve() as srv:
        res = requests.get(
            f"{srv.url}/api/v1/smart-query/observations/compare-balances",
            params={
                "observed_from": "2023-01-01T00:00:00",
                "observed_to": "2023-01-31T23:59:59",
                "limit": 50,
                "offset": 0,
            },
            timeout=100,
        )
    assert res.status_code == 200


def test_at_risk_orders_contract(pact_mock_server: Pact):
    (
        pact_mock_server.upon_receiving("Request at-risk orders")
        .given("At-risk orders data exists")
        .with_request("GET", "/api/v1/smart-query/orders/at-risk")
        .with_query_parameter("horizon_hours", "48")
        .with_query_parameter("min_sla_priority", "0.7")
        .with_query_parameter("top_missing_skus_limit", "5")
        .with_query_parameter("limit", "50")
        .with_query_parameter("offset", "0")
        .will_respond_with(200)
        .with_body(AT_RISK_ORDERS_RESULT, "application/json")
    )

    with pact_mock_server.serve() as srv:
        res = requests.get(
            f"{srv.url}/api/v1/smart-query/orders/at-risk",
            params={
                "horizon_hours": 48,
                "min_sla_priority": 0.7,
                "top_missing_skus_limit": 5,
                "limit": 50,
                "offset": 0,
            },
            timeout=100,
        )
    assert res.status_code == 200
