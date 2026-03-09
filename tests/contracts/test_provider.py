"""
Provider Contract Verification Tests for EnvironmentAPI.

This module validates that the FastAPI backend (Provider) strictly adheres
to the data structures and HTTP expectations defined by the AgentClient (Consumer).

Mechanism:
1. It reads the Consumer-generated JSON contract from the `pacts/` directory.
2. It mocks the internal database "tool" functions to return deterministic fixture data.
3. It spins up a live, isolated FastAPI server using `multiprocessing`.
4. It uses the Pact Verifier to replay the Consumer's recorded HTTP requests
   against the live server and asserts that the actual Pydantic-serialized
   responses match the contract exactly.

By mocking the database layer, these tests isolate the HTTP/serialization
boundary. This ensures tests only fail when a true contract violation occurs
(e.g., a renamed JSON key or altered data type), completely eliminating
flakiness caused by changing local database states.
"""

import multiprocessing
import time
from pathlib import Path
from unittest.mock import patch

import pytest
import requests
import uvicorn
from common.schemas.common import ToolResult
from environment_api.main import app as main_app
from pact import Verifier

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


def run_server():
    """
    Boots the FastAPI application in a dedicated background process.

    Configuration details:
    - `ws="none"`: Disables websocket support. This prevents `DeprecationWarning`
      and unclosed async event loop crashes during the aggressive process termination.
    - `log_level="error"`: Suppresses standard access logs to keep test output readable.
    """
    uvicorn.run(main_app, host="127.0.0.1", port=8001, log_level="error", ws="none")


# The decorators patch the functions exactly where they are imported and executed
# inside the FastAPI router files, not where they are originally defined.
# Note: Python applies multiple decorators from bottom to top, which dictates
# the parameter order in the test function signature.
@patch("environment_api.api.smart_query_routes.procurement.list_suppliers")
@patch("environment_api.api.smart_query_routes.procurement.get_supplier")
@patch("environment_api.api.smart_query_routes.procurement.list_purchase_orders")
@patch("environment_api.api.smart_query_routes.procurement.get_purchase_order")
@patch("environment_api.api.smart_query_routes.procurement.list_po_lines")
@patch("environment_api.api.smart_query_routes.procurement.get_procurement_pipeline_summary")
@patch("environment_api.api.smart_query.get_current_inventory")
@patch("environment_api.api.smart_query.get_shipments_delay_summary")
@patch("environment_api.api.smart_query.compare_observations_to_balances")
@patch("environment_api.api.smart_query.get_at_risk_orders")
def test_provider_complies_with_contract(
    mock_at_risk,
    mock_compare_obs,
    mock_delay_summary,
    mock_inventory,
    mock_pipeline,
    mock_po_lines,
    mock_get_po,
    mock_list_pos,
    mock_get_supplier,
    mock_list_suppliers,
):
    """
    Executes the Pact verification suite against the mocked FastAPI server.

    Execution Flow:
    1. Validates the existence of the consumer contract file to prevent false passes.
    2. Overrides the return values of all data-fetching tools with strict `ToolResult`
       wrappers containing the predefined JSON fixtures.
    3. Starts the Uvicorn server and yields control to the Rust FFI `Verifier`.
    4. Guarantees server termination in a `finally` block to prevent zombie
    processes/port collisions.
    """
    pact_dir = Path.cwd() / "pacts"
    if not pact_dir.exists() or not list(pact_dir.glob("*.json")):
        pytest.fail("No contract files found. Run consumer test first!")

    # Configure the ToolResult returns to strictly match the data in the fixtures
    mock_list_suppliers.return_value = ToolResult(**SUPPLIERS_LIST_RESULT)
    mock_get_supplier.return_value = ToolResult(**SUPPLIER_GET_RESULT)
    mock_list_pos.return_value = ToolResult(**PURCHASE_ORDERS_LIST_RESULT)
    mock_get_po.return_value = ToolResult(**PURCHASE_ORDER_GET_RESULT)
    mock_po_lines.return_value = ToolResult(**PO_LINES_LIST_RESULT)
    mock_pipeline.return_value = ToolResult(**PIPELINE_SUMMARY_RESULT)
    mock_inventory.return_value = ToolResult(**INVENTORY_RESULT)
    mock_delay_summary.return_value = ToolResult(**DELAY_SUMMARY_RESULT)
    mock_compare_obs.return_value = ToolResult(**OBSERVATIONS_RESULT)
    mock_at_risk.return_value = ToolResult(**AT_RISK_ORDERS_RESULT)

    server_process = multiprocessing.Process(target=run_server)
    server_process.start()

    for _ in range(50):
        try:
            requests.get("http://127.0.0.1:8001/", timeout=0.1)
            break
        except requests.exceptions.ConnectionError:
            time.sleep(0.1)
    else:
        server_process.terminate()
        pytest.fail("FastAPI server failed to start within the timeout.")

    try:
        verifier = (
            Verifier("EnvironmentAPI")
            .add_transport(protocol="http", port=8001)
            .add_source(str(pact_dir))
        )
        verifier.verify()
    finally:
        server_process.terminate()
        server_process.join(timeout=2)
        if server_process.is_alive():
            server_process.kill()
            server_process.join()
