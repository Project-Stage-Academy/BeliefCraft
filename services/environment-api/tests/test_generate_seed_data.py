"""
Tests for the SimulationRunner.

Verifies the high-level orchestration of the seeding process:
1. Database reset (metadata drop/create).
2. Phase 1 (Static world build).
3. Phase 2 (Time-series simulation loop).
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from src.data_generator.generate_seed_data import SimulationRunner


@pytest.fixture
def mock_engine():
    """Provides a mocked SQLAlchemy Engine."""
    return MagicMock()


@pytest.fixture
def runner(mock_engine):
    """Initializes SimulationRunner with a mocked engine."""
    return SimulationRunner(mock_engine)


class TestSimulationRunner:
    @patch("src.data_generator.generate_seed_data.Base.metadata")
    def test_reset_database(self, mock_metadata, runner, mock_engine):
        """
        Verifies that the database reset phase drops and recreates tables.
        """
        runner._reset_database()

        mock_metadata.drop_all.assert_called_once_with(bind=mock_engine)
        mock_metadata.create_all.assert_called_once_with(bind=mock_engine)

    @patch("src.data_generator.generate_seed_data.WorldBuilder")
    @patch("src.data_generator.generate_seed_data.settings")
    def test_build_static_world(self, mock_settings, mock_world_cls, runner):
        """
        Verifies Phase 1: Static world build orchestration.
        """
        mock_session = MagicMock()
        mock_settings.simulation.random_seed = 42

        world_instance = mock_world_cls.return_value

        result = runner._build_static_world(mock_session)

        mock_world_cls.assert_called_once_with(mock_session, seed=42)
        world_instance.build_all.assert_called_once()
        mock_session.commit.assert_called_once()
        assert result == world_instance

    @patch("src.data_generator.generate_seed_data.SimulationEngine")
    def test_simulate_history_setup(self, mock_sim_engine_cls, runner):
        """
        Verifies that Phase 2 correctly initializes the SimulationEngine
        with the entities generated in Phase 1.
        """
        mock_session = MagicMock()
        mock_world = MagicMock()
        mock_world.warehouses = [MagicMock()]
        mock_world.products = [MagicMock()]
        mock_world.suppliers = [MagicMock()]

        # We don't want to run the actual loop in this unit test
        runner._run_time_loop = MagicMock()

        runner._simulate_history(mock_session, mock_world, days=10)

        # Check dependency injection into SimulationEngine
        mock_sim_engine_cls.assert_called_once_with(
            session=mock_session,
            warehouses=mock_world.warehouses,
            products=mock_world.products,
            suppliers=mock_world.suppliers
        )
        runner._run_time_loop.assert_called_once()

    @patch("src.data_generator.generate_seed_data.settings")
    def test_run_time_loop_execution(self, mock_settings, runner):
        """
        Verifies the daily loop logic:
        1. Calls engine.tick for every day.
        2. Respects the commit interval.
        """
        mock_session = MagicMock()
        mock_engine = MagicMock()
        mock_settings.simulation.commit_interval = 2

        # 3 days simulation (Today, Today+1, Today+2)
        start_date = datetime(2026, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2026, 1, 3, tzinfo=timezone.utc)

        runner._run_time_loop(mock_session, mock_engine, start_date, end_date)

        # Verify tick was called for each day
        assert mock_engine.tick.call_count == 3

        # Verify commit logic based on interval + final commit
        # Ticks: 0 (commit), 1 (skip), 2 (commit), End (commit)
        assert mock_session.commit.call_count >= 2

    @patch("src.data_generator.generate_seed_data.SessionLocal")
    def test_run_orchestration_failure_rollback(self, mock_session_local, runner):
        """
        Ensures that if an error occurs during simulation,
        the session is rolled back and closed.
        """
        mock_session = mock_session_local.return_value
        runner._reset_database = MagicMock()
        # Trigger an error during Phase 1
        runner._build_static_world = MagicMock(side_effect=RuntimeError("DB Crash"))

        with pytest.raises(RuntimeError, match="DB Crash"):
            runner.run(days=1)

        mock_session.rollback.assert_called_once()
        mock_session.close.assert_called_once()
