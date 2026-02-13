# file: services/environment-api/src/data_generator/logic/sensors.py
"""
Sensor Manager Module.

Responsible for the 'Observer' layer of the simulation.
It generates imperfect, noisy data representing what the digital system "sees"
versus what is physically on the shelf.
"""

import random
from datetime import datetime

from common.logging import get_logger
from sqlalchemy.orm import Session
from src.config_load import settings

from packages.database.src.enums import DeviceStatus, LocationType, ObservationType
from packages.database.src.models import (
    InventoryBalance,
    Location,
    Observation,
    SensorDevice,
    Warehouse,
)

logger = get_logger(__name__)


class SensorManager:
    """
    Simulates the observation layer of the warehouse.

    Instead of perfect database knowledge, this manager generates 'Observations'
    which may be noisy, missing, or biased. This is the dataset the AI agent
    will actually see.
    """

    def __init__(self, session: Session):
        self.session = session
        self.rng = random.Random(settings.simulation.random_seed)  # noqa: S311

    def generate_daily_observations(self, date: datetime, warehouses: list[Warehouse]) -> None:
        """
        Simulates a day of sensing activity across the entire facility.
        """
        obs_count = 0

        for wh in warehouses:
            obs_count += self._process_warehouse_observations(wh, date)

        if obs_count > 0:
            logger.info("sensors_updated", observations_generated=obs_count, date=date.isoformat())

    def _process_warehouse_observations(self, warehouse: Warehouse, date: datetime) -> int:
        """
        Generates observations for a single warehouse based on its active sensors
        and current inventory state.
        """
        active_sensors = self._get_active_sensors(warehouse)
        if not active_sensors:
            return 0

        balances = self._get_positive_inventory(warehouse)
        if not balances:
            return 0

        count = 0
        for balance in balances:
            if self._should_scan_item(balance):
                sensor = self.rng.choice(active_sensors)
                self._create_observation(sensor, balance, date)
                count += 1

        return count

    def _get_active_sensors(self, warehouse: Warehouse) -> list[SensorDevice]:
        """
        Retrieves all sensors currently marked as ACTIVE for the warehouse.
        """
        return [d for d in warehouse.sensor_devices if d.status == DeviceStatus.ACTIVE]

    def _get_positive_inventory(self, warehouse: Warehouse) -> list[InventoryBalance]:
        """
        Retrieves all inventory records with non-zero quantity.
        """
        return (
            self.session.query(InventoryBalance)
            .join(Location)
            .filter(Location.warehouse_id == warehouse.id, InventoryBalance.on_hand > 0)
            .all()
        )

    def _should_scan_item(self, balance: InventoryBalance) -> bool:
        """
        Determines if an item is detected during this simulation tick based on
        its location type.
        """
        if balance.location.type == LocationType.DOCK:
            scan_probability = settings.sensors.scan_probabilities.dock
        else:
            scan_probability = settings.sensors.scan_probabilities.default

        return self.rng.random() <= scan_probability

    def _create_observation(
        self, sensor: SensorDevice, balance: InventoryBalance, date: datetime
    ) -> None:
        """
        Orchestrates the creation of a single observation record.
        """
        observed_qty, confidence, is_missing = self._calculate_observed_values(
            sensor, balance.on_hand
        )

        self._persist_observation(
            sensor=sensor,
            balance=balance,
            observed_qty=observed_qty,
            confidence=confidence,
            is_missing=is_missing,
            date=date,
        )

    def _calculate_observed_values(
        self, sensor: SensorDevice, actual_qty: float
    ) -> tuple[float | None, float, bool]:
        """
        Applies stochastic noise models (Gaussian noise and Bernoulli failure)
        to the actual quantity.
        """
        is_missing = self.rng.random() < sensor.missing_rate

        if is_missing:
            return None, 0.0, True

        cfg = settings.sensors.noise_model

        sigma_units = max(cfg.min_sigma_units, actual_qty * sensor.noise_sigma)

        noise = self.rng.gauss(cfg.noise_mean, sigma_units)

        observed_qty = max(cfg.min_observed_qty, actual_qty + noise)
        confidence = max(
            cfg.min_confidence, cfg.base_confidence - (sensor.noise_sigma * cfg.noise_multiplier)
        )

        return observed_qty, confidence, False

    def _persist_observation(
        self,
        sensor: SensorDevice,
        balance: InventoryBalance,
        observed_qty: float | None,
        confidence: float,
        is_missing: bool,
        date: datetime,
    ) -> None:
        """
        Creates and adds the Observation database record.
        """
        obs = Observation(
            observed_at=date,
            device_id=sensor.id,
            product_id=balance.product_id,
            location_id=balance.location_id,
            obs_type=ObservationType.SCAN,
            observed_qty=observed_qty,
            confidence=confidence,
            is_missing=is_missing,
            reported_noise_sigma=sensor.noise_sigma,
        )
        self.session.add(obs)
