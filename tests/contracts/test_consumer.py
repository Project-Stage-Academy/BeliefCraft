"""
Consumer-Driven Contract Tests for the AgentClient.

These tests define the exact HTTP requests the client will make and the exact
JSON responses it expects. They do not test the real backend.
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
    SUPPLIERS_LIST_RESULT,
)


@pytest.fixture(scope="module")
def pact_mock_server():
    pact = Pact("AgentClient", "EnvironmentAPI")
    yield pact
    pact_dir = Path.cwd() / "pacts"
    pact_dir.mkdir(exist_ok=True)
    pact.write_file(str(pact_dir))


def test_list_suppliers_contract(pact_mock_server: Pact):
    (
        pact_mock_server.upon_receiving("A request to list suppliers")
        .given("Suppliers exist")
        .with_request("GET", "/api/v1/smart-query/procurement/suppliers")
        .with_query_parameter("limit", "100")
        .with_query_parameter("offset", "0")
        .will_respond_with(200)
        .with_body(SUPPLIERS_LIST_RESULT, "application/json")
    )

    with pact_mock_server.serve() as server:
        response = requests.get(
            f"{server.url}/api/v1/smart-query/procurement/suppliers",
            params={"limit": 100, "offset": 0},
            timeout=100,
        )

    assert response.status_code == 200
    assert response.json() == SUPPLIERS_LIST_RESULT


def test_current_inventory_contract(pact_mock_server: Pact):
    (
        pact_mock_server.upon_receiving("A request for current inventory")
        .given("Inventory exists")
        .with_request("GET", "/api/v1/smart-query/inventory/current")
        .with_query_parameter("limit", "50")
        .with_query_parameter("offset", "0")
        .with_query_parameter("include_reserved", "true")
        .will_respond_with(200)
        .with_body(INVENTORY_RESULT, "application/json")
    )

    with pact_mock_server.serve() as server:
        response = requests.get(
            f"{server.url}/api/v1/smart-query/inventory/current",
            params={"limit": 50, "offset": 0, "include_reserved": "true"},
            timeout=100,
        )

    assert response.status_code == 200
    assert response.json() == INVENTORY_RESULT


def test_shipments_delay_summary_contract(pact_mock_server: Pact):
    (
        pact_mock_server.upon_receiving("A request for shipment delay summary")
        .given("Shipment delays exist")
        .with_request("GET", "/api/v1/smart-query/shipments/delay-summary")
        .with_query_parameter("date_from", "2023-01-01T00:00:00")
        .with_query_parameter("date_to", "2023-01-31T23:59:59")
        .will_respond_with(200)
        .with_body(DELAY_SUMMARY_RESULT, "application/json")
    )

    with pact_mock_server.serve() as server:
        response = requests.get(
            f"{server.url}/api/v1/smart-query/shipments/delay-summary",
            params={"date_from": "2023-01-01T00:00:00", "date_to": "2023-01-31T23:59:59"},
            timeout=100,
        )

    assert response.status_code == 200
    assert response.json() == DELAY_SUMMARY_RESULT


def test_compare_balances_contract(pact_mock_server: Pact):
    (
        pact_mock_server.upon_receiving("A request to compare observations to balances")
        .given("Observations exist")
        .with_request("GET", "/api/v1/smart-query/observations/compare-balances")
        .with_query_parameter("observed_from", "2023-01-01T00:00:00")
        .with_query_parameter("observed_to", "2023-01-31T23:59:59")
        .with_query_parameter("limit", "50")
        .with_query_parameter("offset", "0")
        .will_respond_with(200)
        .with_body(OBSERVATIONS_RESULT, "application/json")
    )

    with pact_mock_server.serve() as server:
        response = requests.get(
            f"{server.url}/api/v1/smart-query/observations/compare-balances",
            params={
                "observed_from": "2023-01-01T00:00:00",
                "observed_to": "2023-01-31T23:59:59",
                "limit": 50,
                "offset": 0,
            },
            timeout=100,
        )

    assert response.status_code == 200
    assert response.json() == OBSERVATIONS_RESULT


def test_at_risk_orders_contract(pact_mock_server: Pact):
    (
        pact_mock_server.upon_receiving("A request for at-risk orders")
        .given("At-risk orders exist")
        .with_request("GET", "/api/v1/smart-query/orders/at-risk")
        .with_query_parameter("horizon_hours", "48")
        .with_query_parameter("min_sla_priority", "0.7")
        .with_query_parameter("top_missing_skus_limit", "5")
        .with_query_parameter("limit", "50")
        .with_query_parameter("offset", "0")
        .will_respond_with(200)
        .with_body(AT_RISK_ORDERS_RESULT, "application/json")
    )

    with pact_mock_server.serve() as server:
        response = requests.get(
            f"{server.url}/api/v1/smart-query/orders/at-risk",
            params={
                "horizon_hours": 48,
                "min_sla_priority": 0.7,
                "top_missing_skus_limit": 5,
                "limit": 50,
                "offset": 0,
            },
            timeout=100,
        )

    assert response.status_code == 200
    assert response.json() == AT_RISK_ORDERS_RESULT
