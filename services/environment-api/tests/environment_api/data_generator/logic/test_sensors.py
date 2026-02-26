import random
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from database.enums import LocationType, ObservationType
from database.models import InventoryBalance, Location, Observation, SensorDevice
from environment_api.data_generator.logic.sensors import SensorManager, calculate_sensor_reading


@pytest.fixture
def mock_settings():
    """Provides deterministic configuration bounds for sensor math."""
    with patch("environment_api.data_generator.logic.sensors.settings") as mock_set:
        # Noise Model Config
        mock_set.sensors.noise_model.min_sigma_units = 1.0
        mock_set.sensors.noise_model.noise_mean = 0.0
        mock_set.sensors.noise_model.min_observed_qty = 0.0
        mock_set.sensors.noise_model.min_confidence = 0.1
        mock_set.sensors.noise_model.base_confidence = 1.0
        mock_set.sensors.noise_model.noise_multiplier = 10.0

        # Probability Config
        mock_set.sensors.scan_probabilities.dock = 0.9
        mock_set.sensors.scan_probabilities.default = 0.1
        mock_set.simulation.random_seed = 42
        yield mock_set


@pytest.fixture
def mock_session():
    return MagicMock()


class TestSensorMathLogic:
    def test_calculate_sensor_reading_missing(self, mock_settings):
        """Forces the RNG to trigger the missing data threshold."""
        rng = MagicMock(spec=random.Random)
        rng.random.return_value = 0.05  # Below the 10% missing rate

        obs_qty, confidence, is_missing = calculate_sensor_reading(
            actual_qty=100.0, noise_sigma=0.05, missing_rate=0.10, rng=rng
        )

        assert is_missing is True
        assert obs_qty is None
        assert confidence == 0.0

    def test_calculate_sensor_reading_noisy(self, mock_settings):
        """Verifies Gaussian noise application and confidence decay."""
        rng = MagicMock(spec=random.Random)
        rng.random.return_value = 0.50  # Passes the missing data check
        rng.gauss.return_value = 5.0  # Forces +5 units of noise

        # 100 actual qty, 2% noise sigma
        obs_qty, confidence, is_missing = calculate_sensor_reading(
            actual_qty=100.0, noise_sigma=0.02, missing_rate=0.10, rng=rng
        )

        assert is_missing is False
        assert obs_qty == 105.0  # 100 + 5 noise
        assert confidence == 0.8  # 1.0 base - (0.02 * 10.0 multiplier)

    def test_calculate_sensor_reading_bounds(self, mock_settings):
        """Ensures observations cannot be negative and confidence is floored."""
        rng = MagicMock(spec=random.Random)
        rng.random.return_value = 0.50
        rng.gauss.return_value = -50.0  # Extreme negative noise

        # 10 actual qty with extreme 20% noise sigma
        obs_qty, confidence, is_missing = calculate_sensor_reading(
            actual_qty=10.0, noise_sigma=0.20, missing_rate=0.10, rng=rng
        )

        assert is_missing is False
        assert obs_qty == 0.0  # Bounded from -40.0 to 0.0
        assert confidence == 0.1  # Floored at min_confidence (1.0 - (0.2 * 10) = -1.0 -> 0.1)


class TestSensorManager:
    def test_should_scan_item_dock_vs_default(self, mock_settings, mock_session):
        """Verifies that location type correctly alters scanning probability."""
        manager = SensorManager(mock_session)
        manager.rng = MagicMock()
        manager.rng.random.return_value = 0.50  # 50% roll

        # Setup DOCK balance (90% scan probability)
        dock_loc = Location(type=LocationType.DOCK)
        dock_balance = InventoryBalance(location=dock_loc)

        # Setup SHELF balance (10% scan probability)
        shelf_loc = Location(type=LocationType.SHELF)
        shelf_balance = InventoryBalance(location=shelf_loc)

        # 0.50 <= 0.90 (True)
        assert manager._should_scan_item(dock_balance) is True
        # 0.50 <= 0.10 (False)
        assert manager._should_scan_item(shelf_balance) is False

    @patch("environment_api.data_generator.logic.sensors.calculate_sensor_reading")
    def test_manager_persists_observation_records(self, mock_calc, mock_settings, mock_session):
        """Verifies true state is correctly translated into noisy observation DB records."""
        # Force the math logic to return a specific noisy output
        mock_calc.return_value = (98.0, 0.9, False)

        manager = SensorManager(mock_session)
        date = datetime.now(tz=UTC)

        sensor = SensorDevice(id="sensor-1", noise_sigma=0.05, missing_rate=0.01)
        balance = InventoryBalance(product_id="prod-1", location_id="loc-1", on_hand=100.0)

        manager._create_observation(sensor, balance, date)

        # Verify Observation DB entity structure
        mock_session.add.assert_called_once()
        obs = mock_session.add.call_args[0][0]

        assert isinstance(obs, Observation)
        assert obs.observed_at == date
        assert obs.device_id == "sensor-1"
        assert obs.product_id == "prod-1"
        assert obs.location_id == "loc-1"
        assert obs.obs_type == ObservationType.SCAN
        assert obs.observed_qty == 98.0
        assert obs.confidence == 0.9
        assert obs.is_missing is False
        assert obs.reported_noise_sigma == 0.05
