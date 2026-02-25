from datetime import UTC, datetime

import pytest
from database.enums import DeviceType, DistFamily, LeadtimeScope, ObservationType
from database.logistics import LeadtimeModel, Supplier
from database.observations import Observation, SensorDevice
from database.orders import Order
from sqlalchemy.exc import IntegrityError


@pytest.mark.parametrize(
    "factory_fn",
    [
        lambda w, p, ctx, v: Supplier(name=f"Sup-{v}", region="US", reliability_score=v),
        lambda w, p, ctx, v: Order(customer_name="A", sla_priority=v),
        lambda w, p, ctx, v: LeadtimeModel(
            scope=LeadtimeScope.SUPPLIER, dist_family=DistFamily.NORMAL, p_rare_delay=v
        ),
        lambda w, p, ctx, v: SensorDevice(
            warehouse_id=w.id, device_type=DeviceType.CAMERA, missing_rate=v
        ),
        lambda w, p, ctx, v: Observation(
            observed_at=datetime.now(UTC),
            device_id=ctx["device"].id,
            product_id=p.id,
            location_id=ctx["dock"].id,
            obs_type=ObservationType.SCAN,
            confidence=v,
        ),
    ],
)
@pytest.mark.parametrize("invalid_value", [-0.1, 1.1])
def test_between_zero_one_constraints(db_session, seed_base_world, factory_fn, invalid_value):
    """
    Verify CHECK constraints strictly bound percentage/probability fields to [0, 1].

    Why this is important: Machine learning models and probability
    calculations (like `missing_rate` or `confidence`) will crash or behave
    unpredictably if fed values outside the standard mathematical domain.
    """
    w = seed_base_world["warehouse"]
    p = seed_base_world["product"]
    dock = seed_base_world["dock"]

    dev = SensorDevice(warehouse_id=w.id, device_type=DeviceType.CAMERA)
    db_session.add(dev)
    db_session.flush()

    ctx = {"device": dev, "dock": dock}

    obj = factory_fn(w, p, ctx, invalid_value)
    db_session.add(obj)
    with pytest.raises(IntegrityError):
        db_session.commit()
