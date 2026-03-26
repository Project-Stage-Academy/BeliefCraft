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
        product_id = uuid.uuid4()
        command = ReceiptCommand(
            location=mock_location,
            product_id=product_id,
            date=datetime.now(tz=UTC),
            qty=100.0,
            ref_id=uuid.uuid4(),
        )
        ledger.record_receipt(command)

        # Verify atomic upsert was executed
        mock_session.execute.assert_called_once()

        # Verify Audit Trail
        assert mock_session.add.call_count == 1
        move = mock_session.add.call_args[0][0]
        assert isinstance(move, InventoryMove)
        assert move.move_type == MoveType.INBOUND

        assert move.qty == 100.0
        assert move.from_location_id is None
        assert move.to_location_id == mock_location.id

    def test_record_receipt_existing_product(self, ledger, mock_session, mock_location):
        product_id = uuid.uuid4()
        command = ReceiptCommand(
            location=mock_location,
            product_id=product_id,
            date=datetime.now(tz=UTC),
            qty=10.0,
            ref_id=uuid.uuid4(),
        )
        ledger.record_receipt(command)

        mock_session.execute.assert_called_once()
        assert mock_session.add.call_count == 1

    def test_record_issuance_logic(self, ledger, mock_session, mock_location):
        product_id = uuid.uuid4()
        existing_balance = InventoryBalance(
            product_id=product_id, location_id=mock_location.id, on_hand=100.0
        )

        # Mock the locked query chain
        mock_session.query().filter_by().with_for_update().first.return_value = existing_balance

        command = ReceiptCommand(
            location=mock_location,
            product_id=product_id,
            date=datetime.now(tz=UTC),
            qty=30.0,
            ref_id=uuid.uuid4(),
        )
        ledger.record_issuance(command)

        # Verify decrement
        assert existing_balance.on_hand == 70.0

        # Verify move record
        assert mock_session.add.call_count == 1
        move = mock_session.add.call_args[0][0]
        assert move.move_type == MoveType.OUTBOUND
        assert move.qty == 30.0
        assert move.reason_code == "CUSTOMER_ORDER"

    def test_record_issuance_insufficient_stock(self, ledger, mock_session, mock_location):
        """Verifies that attempting to issue more stock than available raises an error."""
        product_id = uuid.uuid4()
        existing_balance = InventoryBalance(
            product_id=product_id, location_id=mock_location.id, on_hand=10.0
        )
        mock_session.query().filter_by().with_for_update().first.return_value = existing_balance

        command = ReceiptCommand(
            location=mock_location,
            product_id=product_id,
            date=datetime.now(tz=UTC),
            qty=30.0,
            ref_id=uuid.uuid4(),
        )

        with pytest.raises(ValueError, match="Insufficient stock"):
            ledger.record_issuance(command)
