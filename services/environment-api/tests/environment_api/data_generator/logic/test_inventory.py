"""
Tests for the InventoryLedger.

Verifies the 'accounting' logic of the simulation: ensuring that physical
stock increases/decreases correctly update the balance records and always
generate an immutable audit log (InventoryMove).
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from database.enums import MoveType
from database.models import InventoryBalance, InventoryMove, Location
from environment_api.data_generator.logic.inventory import InventoryLedger, ReceiptCommand


@pytest.fixture
def mock_session():
    """Provides a mocked SQLAlchemy session."""
    return MagicMock()


@pytest.fixture
def ledger(mock_session):
    """Initializes the InventoryLedger with a mocked session."""
    return InventoryLedger(mock_session)


@pytest.fixture
def mock_location():
    """Provides a mocked Location entity."""
    loc = MagicMock(spec=Location)
    loc.id = uuid.uuid4()
    return loc


class TestInventoryLedger:
    def test_record_receipt_new_product(self, ledger, mock_session, mock_location):
        """
        Verifies that receiving a product for the first time creates a
        new balance record and logs the movement.
        """
        product_id = uuid.uuid4()
        ref_id = uuid.uuid4()
        date = datetime.now(tz=UTC)
        qty = 100.0

        # Mock database query returning None (no existing balance)
        mock_session.query().filter_by().first.return_value = None

        command = ReceiptCommand(
            location=mock_location, product_id=product_id, date=date, qty=qty, ref_id=ref_id
        )
        ledger.record_receipt(command)

        # 1. Verify Balance Initialization
        # We expect 2 calls to session.add: one for Balance, one for Move
        assert mock_session.add.call_count == 2

        balance = mock_session.add.call_args_list[0][0][0]
        assert isinstance(balance, InventoryBalance)
        assert balance.on_hand == qty
        assert balance.product_id == product_id
        assert balance.location_id == mock_location.id

        # 2. Verify Audit Trail
        move = mock_session.add.call_args_list[1][0][0]
        assert isinstance(move, InventoryMove)
        assert move.move_type == MoveType.INBOUND
        assert move.qty == qty

    def test_record_receipt_existing_product(self, ledger, mock_session, mock_location):
        """
        Verifies that receiving an existing product increments the
        current balance and logs the movement.
        """
        product_id = uuid.uuid4()
        existing_balance = InventoryBalance(
            product_id=product_id, location_id=mock_location.id, on_hand=50.0
        )
        mock_session.query().filter_by().first.return_value = existing_balance

        command = ReceiptCommand(
            location=mock_location,
            product_id=product_id,
            date=datetime.now(tz=UTC),
            qty=10,
            ref_id=uuid.uuid4(),
        )
        ledger.record_receipt(command)

        # Verify balance was updated
        assert existing_balance.on_hand == 60.0
        # Verify session.add was only called once (for the move, balance was already in session)
        assert mock_session.add.call_count == 1

    def test_record_issuance_logic(self, ledger, mock_session, mock_location):
        """
        Verifies that issuing (shipping) stock decrements the balance
        and creates an OUTBOUND movement record.
        """
        product_id = uuid.uuid4()
        existing_balance = InventoryBalance(
            product_id=product_id, location_id=mock_location.id, on_hand=100.0
        )
        mock_session.query().filter_by().first.return_value = existing_balance

        command = ReceiptCommand(
            location=mock_location,
            product_id=uuid.uuid4(),
            date=datetime.now(tz=UTC),
            qty=30,
            ref_id=uuid.uuid4(),
        )
        ledger.record_issuance(command)

        # Verify decrement
        assert existing_balance.on_hand == 70.0

        # Verify move record
        move = mock_session.add.call_args[0][0]
        assert isinstance(move, InventoryMove)
        assert move.move_type == MoveType.OUTBOUND
        assert move.qty == 30.0  # Logged as positive delta in movement table usually
        assert move.reason_code == "CUSTOMER_ORDER"
