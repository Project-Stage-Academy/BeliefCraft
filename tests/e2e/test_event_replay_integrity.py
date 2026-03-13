from datetime import UTC, datetime, timedelta

import pytest
from database.enums import MoveType
from database.models import InventoryBalance, InventoryMove
from environment_api.data_generator.logic.inventory import InventoryLedger, ReceiptCommand
from sqlalchemy import func, select
from sqlalchemy.orm import Session


@pytest.mark.integration
def test_inventory_event_replay_matches_materialized_state(
    db_session: Session, seed_base_world: dict
) -> None:
    """
    Validates Event Sourcing Integrity.

    Scenario:
    Executes a chronological series of inbound and outbound physical movements.
    Asserts that the sum of the immutable event log (InventoryMove) perfectly
    matches the mutable materialized state (InventoryBalance).
    """
    # 1. Arrange
    loc = seed_base_world["dock"]
    prod = seed_base_world["product"]
    wh = seed_base_world["warehouse"]

    ledger = InventoryLedger(db_session)
    base_time = datetime.now(UTC)

    # 2. Act: Execute a sequence of events over time
    events = [
        ("RECEIPT", 100.0, base_time),  # +100
        ("ISSUE", 30.0, base_time + timedelta(hours=1)),  # -30
        ("RECEIPT", 50.0, base_time + timedelta(hours=2)),  # +50
        ("ISSUE", 15.0, base_time + timedelta(hours=3)),  # -15
    ]

    for action, qty, timestamp in events:
        command = ReceiptCommand(
            location=loc,
            product_id=prod.id,
            qty=qty,
            date=timestamp,
            ref_id=wh.id,  # Dummy reference ID
        )
        if action == "RECEIPT":
            ledger.record_receipt(command)
        else:
            ledger.record_issuance(command)

        db_session.flush()

    # 3. Assert: Materialized State (What the system currently thinks it has)
    balance = db_session.execute(
        select(InventoryBalance).where(
            InventoryBalance.product_id == prod.id, InventoryBalance.location_id == loc.id
        )
    ).scalar_one()

    expected_final_qty = 100.0 - 30.0 + 50.0 - 15.0  # 105.0
    assert balance.on_hand == expected_final_qty

    # 4. Assert: Event Replay (Reconstructing state purely from the append-only log)
    # Math: SUM(INBOUND) - SUM(OUTBOUND)
    inbound_qty = db_session.execute(
        select(func.coalesce(func.sum(InventoryMove.qty), 0)).where(
            InventoryMove.product_id == prod.id, InventoryMove.move_type == MoveType.INBOUND
        )
    ).scalar_one()

    outbound_qty = db_session.execute(
        select(func.coalesce(func.sum(InventoryMove.qty), 0)).where(
            InventoryMove.product_id == prod.id, InventoryMove.move_type == MoveType.OUTBOUND
        )
    ).scalar_one()

    reconstructed_qty = inbound_qty - outbound_qty

    assert reconstructed_qty == expected_final_qty
    assert reconstructed_qty == balance.on_hand
