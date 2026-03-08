"""
Provider Contract Verification Tests.
Mocks the exact import paths used in your FastAPI routers.
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
    uvicorn.run(main_app, host="127.0.0.1", port=8001, log_level="error", ws="none")


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
    time.sleep(2)

    try:
        verifier = (
            Verifier("EnvironmentAPI")
            .add_transport(protocol="http", port=8001)
            .add_source(str(pact_dir))
        )
        verifier.verify()
    finally:
        server_process.terminate()
        server_process.join()
