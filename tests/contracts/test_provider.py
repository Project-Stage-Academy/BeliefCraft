"""
Provider Contract Verification Tests for the EnvironmentAPI.

This script boots the local FastAPI server and replays the interactions
recorded in the Consumer's JSON contract against it.
"""

import multiprocessing
import time
from pathlib import Path
from unittest.mock import patch

import pytest
import uvicorn
from common.schemas.common import ToolResult
from environment_api.main import app as main_app
from pact import Verifier

from .fixtures import (
    AT_RISK_ORDER_FIXTURE,
    DELAY_SUMMARY_FIXTURE,
    INVENTORY_FIXTURE,
    OBSERVATIONS_FIXTURE,
    SUPPLIER_FIXTURE,
)


def run_server():
    """
    Boots the FastAPI application in a separate process.
    Websockets are disabled to prevent async loop warnings during teardown.
    """
    uvicorn.run(main_app, host="127.0.0.1", port=8001, log_level="error", ws="none")


# Why this change is important: Contract tests verify the HTTP serialization layer
# (FastAPI/Pydantic), not the database logic. By patching the underlying tools,
# we guarantee the API returns the exact fixture data the contract expects,
# preventing flaky tests caused by live database state changes.
# Note: Python applies @patch decorators bottom-to-top.
@patch("environment_api.api.smart_query_routes.procurement.list_suppliers")
@patch("environment_api.smart_query_builder.tools.get_current_inventory")
@patch("environment_api.smart_query_builder.tools.get_shipments_delay_summary")
@patch("environment_api.smart_query_builder.tools.compare_observations_to_balances")
@patch("environment_api.smart_query_builder.tools.get_at_risk_orders")
def test_provider_complies_with_contract(
    mock_at_risk, mock_compare_obs, mock_delay_summary, mock_inventory, mock_suppliers
):
    """
    Verifies the Provider against all interactions defined in the Pact file.
    """
    pact_dir = Path.cwd() / "pacts"

    # Fails explicitly if the consumer test hasn't generated the required file
    if not pact_dir.exists() or not list(pact_dir.glob("*.json")):
        pytest.fail(f"No contract files found in {pact_dir}. Run the consumer test first!")

    # 1. Inject deterministic fixture data into the mocked endpoints
    mock_suppliers.return_value = ToolResult(data=[SUPPLIER_FIXTURE], message="Success")
    mock_inventory.return_value = ToolResult(data=[INVENTORY_FIXTURE], message="Success")
    mock_delay_summary.return_value = ToolResult(data=[DELAY_SUMMARY_FIXTURE], message="Success")
    mock_compare_obs.return_value = ToolResult(data=[OBSERVATIONS_FIXTURE], message="Success")
    mock_at_risk.return_value = ToolResult(data=[AT_RISK_ORDER_FIXTURE], message="Success")

    # 2. Start the FastAPI server in the background
    server_process = multiprocessing.Process(target=run_server)
    server_process.start()
    time.sleep(2)  # Allow Uvicorn time to bind to the port

    try:
        # 3. Replay the contract file against the running server
        verifier = (
            Verifier("EnvironmentAPI")
            .add_transport(protocol="http", port=8001)
            .add_source(str(pact_dir))
        )
        verifier.verify()
    finally:
        # 4. Ensure the server is killed even if the verification fails
        server_process.terminate()
        server_process.join()
