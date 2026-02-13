"""
Tests for the SimulationEngine.

Focuses on the 'Game Loop' orchestration: verifying that the tick method
triggers each subsystem (Inbound, Outbound, Replenishment, Sensors)
in the strictly required order to maintain causal integrity.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from src.data_generator.simulation_engine import SimulationEngine


@pytest.fixture
def mock_session():
    """Provides a mocked SQLAlchemy session."""
    return MagicMock()


@pytest.fixture
def dummy_data():
    """Provides lists of dummy entities for engine initialization."""
    return [MagicMock()], [MagicMock()], [MagicMock()]


@pytest.fixture
def engine(mock_session, dummy_data):
    """
    Initializes the SimulationEngine with mocked managers to isolate
    the orchestration logic.
    """
    warehouses, products, suppliers = dummy_data

    # We patch the managers so we can verify the call sequence
    with patch("src.data_generator.simulation_engine.InboundManager"), \
        patch("src.data_generator.simulation_engine.OutboundManager"), \
        patch("src.data_generator.simulation_engine.ReplenishmentManager"), \
        patch("src.data_generator.simulation_engine.SensorManager"):
        return SimulationEngine(mock_session, warehouses, products, suppliers)


class TestSimulationEngine:
    def test_engine_initialization(self, engine, dummy_data):
        """
        Verifies that all managers are correctly instantiated during init.
        """
        warehouses, products, suppliers = dummy_data
        assert engine.warehouses == warehouses
        assert engine.products == products
        assert engine.suppliers == suppliers

        # Verify all managers were created
        assert engine.inbound_manager is not None
        assert engine.outbound_manager is not None
        assert engine.replenishment_manager is not None
        assert engine.sensor_manager is not None

    def test_tick_order_of_operations(self, engine, mock_session):
        """
        Verifies the 'Physics Engine' sequence. The order must be:
        1. Inbound -> 2. Outbound -> 3. Replenishment -> 4. Sensors
        """
        current_date = datetime(2024, 5, 20)

        # Use a Manager to track call order across multiple mocks
        call_tracker = MagicMock()
        engine.inbound_manager.process_daily_arrivals = call_tracker.inbound
        engine.outbound_manager.process_daily_demand = call_tracker.outbound
        engine.replenishment_manager.review_stock_levels = call_tracker.replenishment
        engine.sensor_manager.generate_daily_observations = call_tracker.sensors

        engine.tick(current_date)

        # Verify call order
        expected_calls = [
            pytest.mark.inbound(current_date),
            pytest.mark.outbound(current_date, engine.warehouses, engine.products),
            pytest.mark.replenishment(current_date, engine.warehouses, engine.products),
            pytest.mark.sensors(current_date, engine.warehouses)
        ]

        # Check that they were called in the exact sequence defined in the tick method
        call_names = [call[0] for call in call_tracker.method_calls]
        assert call_names == ['inbound', 'outbound', 'replenishment', 'sensors']

    def test_tick_persists_changes(self, engine, mock_session):
        """
        Verifies that the engine flushes the session at the end of every tick.
        """
        engine.tick(datetime.now(tzinfo=timezone.utc))
        mock_session.flush.assert_called_once()
