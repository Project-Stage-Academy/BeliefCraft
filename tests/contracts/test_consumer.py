"""
Consumer-Driven Contract Tests for AgentClient.

This module defines the expectations of the AgentClient (the Consumer) when communicating
with the EnvironmentAPI (the Provider). Running these tests does not hit a real backend;
instead, it spins up a local Rust-backed mock server that listens for exact HTTP requests
and returns predefined JSON fixtures.

Why this is important:
By defining exactly what HTTP paths, query parameters, and JSON schemas the client code
can handle, we generate a formal contract (`pacts/AgentClient-EnvironmentAPI.json`).
This contract is later used to test the backend API, ensuring the backend team can never
accidentally deploy a change (like renaming a field or changing a data type) that would
break this client.
"""

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
    """
    Initializes the Pact mock server and handles contract file generation.

    Why this configuration is important:
    1. Scope: Defaulting to `scope="function"` ensures a brand new Pact FFI handle is created
       and destroyed for every test. Sharing a handle across multiple tests causes state
       collision errors in the Rust core.
    2. Teardown: Pact V4 requires an explicit `write_file()` command after the interaction
       is recorded to flush the JSON to disk. The file is appended to automatically.
    """
    pact = Pact("AgentClient", "EnvironmentAPI")
    yield pact

    pact_dir = Path.cwd() / "pacts"
    pact_dir.mkdir(exist_ok=True)
    pact.write_file(str(pact_dir))


def test_list_suppliers_contract(pact_mock_server: Pact):
    """
    Verifies the consumer's ability to request a paginated list of suppliers.
    Ensures the `limit` and `offset` query parameters are formatted correctly
    and the client can parse the `SUPPLIERS_LIST_RESULT` schema.
    """
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
    """
    Verifies the consumer's ability to fetch a single supplier by UUID.
    Defines the exact path routing required to retrieve `SUPPLIER_GET_RESULT`.
    """
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
    """
    Verifies the consumer's ability to request a paginated list of purchase orders.
    Locks in the expected response schema containing PO metadata and status fields.
    """
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
    """
    Verifies the consumer's ability to fetch a single purchase order by its ID.
    Ensures path parameter injection functions correctly on the client side.
    """
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
    """
    Verifies the consumer can filter PO lines by a specific `purchase_order_id`.
    Validates the structure of individual line items, including quantities and SKUs.
    """
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
    """
    Verifies the consumer's ability to fetch aggregated procurement data.
    Ensures the `group_by` enum is correctly serialized into the query string.
    """
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
    """
    Verifies the consumer can fetch real-time inventory balances.
    Confirms the client correctly handles the list-based JSON payload for stock levels.
    """
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
    """
    Verifies the consumer's ability to request shipment delay metrics within a timeframe.
    Crucially asserts that ISO-8601 datetime strings are properly URL-encoded in the query.
    """
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
    """
    Verifies the consumer can fetch data comparing physical observations to system balances.
    Validates that multiple complex query parameters (dates + pagination) construct properly.
    """
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
    """
    Verifies the consumer can request orders flagged as fulfillment risks.
    Ensures float values (like `min_sla_priority`) are transmitted and parsed correctly.
    """
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
            timeout=5,
        )
    assert res.status_code == 200
