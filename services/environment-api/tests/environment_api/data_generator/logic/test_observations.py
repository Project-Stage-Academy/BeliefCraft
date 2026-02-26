import uuid
from datetime import UTC, datetime, timedelta

from common.schemas.observations import CompareObservationsToBalancesRequest
from database.enums import LocationType, ObservationType, QualityStatus
from database.models import (
    InventoryBalance,
    Location,
    Observation,
    Product,
    SensorDevice,
    Warehouse,
)
from environment_api.smart_query_builder.repo.observations import fetch_observation_vs_balance_rows
from sqlalchemy.orm import Session


def test_compare_observations_to_balances_discrepancy_math(db_session: Session):
    """
    Verifies the statistical discrepancy between the True State (InventoryBalance)
    and the Noisy State (Weighted average of Observations).
    """
    # 1. Setup True State
    wh = Warehouse(id=uuid.uuid4(), name="WH-TEST", region="NA", tz="UTC")
    loc = Location(
        id=uuid.uuid4(), warehouse_id=wh.id, code="LOC-1", type=LocationType.BIN, capacity_units=100
    )
    prod = Product(id=uuid.uuid4(), sku="SKU-NOISE-TEST", name="Test Item", category="Parts")
    device = SensorDevice(id=uuid.uuid4(), warehouse_id=wh.id, device_type="scale")

    # True State: Exactly 100 units physically exist
    balance = InventoryBalance(
        product_id=prod.id,
        location_id=loc.id,
        on_hand=100.0,
        reserved=0.0,
        quality_status=QualityStatus.OK,
    )

    db_session.add_all([wh, loc, prod, device, balance])
    db_session.flush()

    base_time = datetime.now(tz=UTC)

    # 2. Inject Noisy Observations
    # Math: (110 * 0.8 + 90 * 0.2) / (0.8 + 0.2) = (88 + 18) / 1.0 = 106.0
    obs1 = Observation(
        observed_at=base_time,
        device_id=device.id,
        product_id=prod.id,
        location_id=loc.id,
        obs_type=ObservationType.SCAN,
        observed_qty=110.0,
        confidence=0.8,
        is_missing=False,
    )
    obs2 = Observation(
        observed_at=base_time + timedelta(minutes=5),
        device_id=device.id,
        product_id=prod.id,
        location_id=loc.id,
        obs_type=ObservationType.SCAN,
        observed_qty=90.0,
        confidence=0.2,
        is_missing=False,
    )

    db_session.add_all([obs1, obs2])
    db_session.commit()

    # 3. Execute Smart Query
    request = CompareObservationsToBalancesRequest(
        observed_from=base_time - timedelta(minutes=10),
        observed_to=base_time + timedelta(minutes=10),
        limit=10,
        offset=0,
    )

    rows = fetch_observation_vs_balance_rows(db_session, request)

    # 4. Assert Mathematical Integrity
    assert len(rows) == 1
    row = rows[0]

    assert row["on_hand"] == 100.0  # True State
    assert row["observed_estimate"] == 106.0  # Noisy State Estimate
    assert row["discrepancy"] == 6.0  # Delta (Estimate - True)
    assert row["obs_count"] == 2
