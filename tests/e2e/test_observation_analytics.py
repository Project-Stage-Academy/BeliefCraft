# file: tests/e2e/test_observation_analytics.py
from datetime import UTC, datetime, timedelta

import pytest
from database.enums import DeviceStatus, DeviceType, ObservationType  # Added Enums
from database.models import InventoryBalance, Observation, SensorDevice  # Added SensorDevice
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


@pytest.mark.integration
def test_compare_observations_to_balances_discrepancy_math(
    client: TestClient, db_session: Session, seed_base_world: dict
) -> None:
    """
    Validates the mathematical accuracy of the discrepancy reporting tool.
    ... [same docstring] ...
    """
    # 1. Arrange: Setup Context from Fixture
    wh = seed_base_world["warehouse"]
    loc = seed_base_world["dock"]
    prod = seed_base_world["product"]
    now = datetime.now(UTC)

    # Seed a Sensor Device (Required for Observation NOT NULL constraint)
    sensor = SensorDevice(
        warehouse_id=wh.id,
        device_type=DeviceType.CAMERA,
        status=DeviceStatus.ACTIVE,
        noise_sigma=0.05,
        missing_rate=0.01,
    )
    db_session.add(sensor)
    db_session.flush()  # Get the sensor.id

    # Seed the "Physical Truth" (The Ledger)
    balance = InventoryBalance(location_id=loc.id, product_id=prod.id, on_hand=100.0, reserved=0)
    db_session.add(balance)

    # Seed "Sensor Observations" using the seeded sensor.id
    high_conf_obs = Observation(
        observed_at=now,
        device_id=sensor.id,  # <--- Added this
        product_id=prod.id,
        location_id=loc.id,
        obs_type=ObservationType.SCAN,
        observed_qty=90.0,
        confidence=0.9,
        is_missing=False,
    )
    low_conf_obs = Observation(
        observed_at=now,
        device_id=sensor.id,  # <--- Added this
        product_id=prod.id,
        location_id=loc.id,
        obs_type=ObservationType.SCAN,
        observed_qty=110.0,
        confidence=0.1,
        is_missing=False,
    )
    db_session.add_all([high_conf_obs, low_conf_obs])
    db_session.flush()

    # 2. Act
    response = client.get(
        "/api/v1/smart-query/observations/compare-balances",
        params={
            "observed_from": (now - timedelta(minutes=5)).isoformat(),
            "observed_to": (now + timedelta(minutes=5)).isoformat(),
            "warehouse_id": str(wh.id),
        },
    )

    # 3. Assert
    assert response.status_code == 200
    results = response.json()["data"]
    assert len(results) > 0
    data = results[0]

    # Math: ((90 * 0.9) + (110 * 0.1)) / (0.9 + 0.1) = 92.0
    assert data["observed_estimate"] == 92.0
    assert data["discrepancy"] == -8.0
