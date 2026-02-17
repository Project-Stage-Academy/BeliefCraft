"""
Tests for the SimulationEngine.

Focuses on the 'Game Loop' orchestration: verifying that the tick method
triggers each subsystem (Inbound, Outbound, Replenishment, Sensors)
in the strictly required order to maintain causal integrity.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from environment_api.data_generator.simulation_engine import SimulationContext, SimulationEngine


@pytest.fixture
def mock_session():
    return MagicMock()


@pytest.fixture
def dummy_data():
    return [MagicMock()], [MagicMock()], [MagicMock()]


@pytest.fixture
def engine(mock_session, dummy_data):
    """
    Initializes the SimulationEngine with mocked processors.
    This bypasses the real managers entirely to test the orchestration loop.
    """
    warehouses, products, suppliers = dummy_data

    # Create mocks for the new Processor classes
    mock_processors = [
        MagicMock(name="InboundProcessor"),
        MagicMock(name="OutboundProcessor"),
        MagicMock(name="ReplenishmentProcessor"),
        MagicMock(name="SensorProcessor"),
    ]

    # Inject the mock processors via the constructor
    return SimulationEngine(
        mock_session, warehouses, products, suppliers, processors=mock_processors
    )


class TestSimulationEngine:
    def test_engine_initialization(self, engine, dummy_data):
        """Verifies that attributes are stored correctly."""
        warehouses, products, suppliers = dummy_data
        assert engine.warehouses == warehouses
        assert engine.products == products
        assert engine.suppliers == suppliers
        assert len(engine.processors) == 4

    def test_tick_order_of_operations(self, engine):
        """
        Verifies the Strategy execution sequence.
        The engine must call .execute() on each processor in the list order.
        """
        current_date = datetime(2024, 5, 20, tzinfo=UTC)

        # We use a manager to track call order across the processor list
        call_tracker = MagicMock()
        for i, processor in enumerate(engine.processors):
            # Point each mock's execute to the tracker
            processor.execute = getattr(call_tracker, f"step_{i}")

        engine.tick(current_date)

        # Verify the sequence of execution
        call_names = [call[0] for call in call_tracker.method_calls]
        assert call_names == ["step_0", "step_1", "step_2", "step_3"]

    def test_tick_passes_correct_context(self, engine, mock_session):
        """
        Verifies that each processor receives a properly populated SimulationContext.
        """
        current_date = datetime(2024, 5, 20, tzinfo=UTC)
        engine.tick(current_date)

        for processor in engine.processors:
            # Check the first argument of the call
            args, _ = processor.execute.call_args
            context = args[0]

            assert isinstance(context, SimulationContext)
            assert context.current_date == current_date
            assert context.session == mock_session
            assert context.warehouses == engine.warehouses

    def test_tick_persists_changes(self, engine, mock_session):
        """Verifies session flush happens after the pipeline finishes."""
        engine.tick(datetime.now(tz=UTC))
        mock_session.flush.assert_called_once()
