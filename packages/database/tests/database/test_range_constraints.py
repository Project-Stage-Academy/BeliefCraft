from datetime import UTC, datetime

import pytest
from database.enums import DeviceType, DistFamily, LeadtimeScope, ObservationType
from database.logistics import LeadtimeModel, Supplier
from database.observations import Observation, SensorDevice
from database.orders import Order
from sqlalchemy.exc import IntegrityError


@pytest.fixture
def prob_constraint_ctx(db_session, seed_base_world):
    """Provides the dependent entities required for probability constraint testing."""
    w = seed_base_world["warehouse"]

    dev = SensorDevice(warehouse_id=w.id, device_type=DeviceType.CAMERA)
    db_session.add(dev)
    db_session.flush()

    return {
        "warehouse": w,
        "product": seed_base_world["product"],
        "dock": seed_base_world["dock"],
        "device": dev,
    }


PROBABILITY_FACTORIES = [
    lambda ctx, v: Supplier(name=f"Sup-{v}", region="US", reliability_score=v),
    lambda ctx, v: Order(customer_name="A", sla_priority=v),
    lambda ctx, v: LeadtimeModel(
        scope=LeadtimeScope.SUPPLIER, dist_family=DistFamily.NORMAL, p_rare_delay=v
    ),
    lambda ctx, v: SensorDevice(
        warehouse_id=ctx["warehouse"].id, device_type=DeviceType.CAMERA, missing_rate=v
    ),
    lambda ctx, v: Observation(
        observed_at=datetime.now(UTC),
        device_id=ctx["device"].id,
        product_id=ctx["product"].id,
        location_id=ctx["dock"].id,
        obs_type=ObservationType.SCAN,
        confidence=v,
    ),
]


@pytest.mark.parametrize("invalid_value", [-1.0, -0.001, 1.001, 2.0])
@pytest.mark.parametrize("factory_fn", PROBABILITY_FACTORIES)
def test_between_zero_one_constraints_invalid(
    db_session, prob_constraint_ctx, factory_fn, invalid_value
):
    """
    Verify CHECK constraints strictly reject values outside the [0, 1] domain.
    """
    obj = factory_fn(prob_constraint_ctx, invalid_value)
    db_session.add(obj)

    with pytest.raises(IntegrityError):
        db_session.commit()


@pytest.mark.parametrize("valid_value", [0.0, 0.5, 1.0])
@pytest.mark.parametrize("factory_fn", PROBABILITY_FACTORIES)
def test_between_zero_one_constraints_valid(
    db_session, prob_constraint_ctx, factory_fn, valid_value
):
    """
    Verify CHECK constraints permit the exact boundary values 0.0 and 1.0.
    """
    obj = factory_fn(prob_constraint_ctx, valid_value)
    db_session.add(obj)

    db_session.commit()
