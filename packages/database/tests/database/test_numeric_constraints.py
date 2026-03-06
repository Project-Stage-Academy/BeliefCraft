from datetime import UTC, datetime

import pytest
from database.enums import (
    DeviceType,
    DistFamily,
    LeadtimeScope,
    LocationType,
    MoveType,
    ObservationType,
    TransportMode,
)
from database.inventory import InventoryBalance, InventoryMove, Location, Product
from database.logistics import LeadtimeModel, Route, Warehouse
from database.observations import Observation, SensorDevice
from database.orders import Order, OrderLine, POLine, PurchaseOrder
from sqlalchemy.exc import IntegrityError


@pytest.fixture
def constraint_ctx(db_session, seed_base_world):
    """Provides the dependent entities required for constraint testing."""
    w = seed_base_world["warehouse"]
    sup = seed_base_world["supplier"]

    w2 = Warehouse(name="W2", region="A", tz="UTC")
    order = Order(customer_name="A")
    po = PurchaseOrder(supplier_id=sup.id, destination_warehouse_id=w.id)
    dev = SensorDevice(warehouse_id=w.id, device_type=DeviceType.CAMERA)

    db_session.add_all([w2, order, po, dev])
    db_session.flush()

    return {
        "warehouse": w,
        "product": seed_base_world["product"],
        "dock": seed_base_world["dock"],
        "w2": w2,
        "order": order,
        "po": po,
        "device": dev,
    }


INT_FACTORIES = [
    lambda ctx, v: Product(sku=f"P-{v}", name="A", category="A", shelf_life_days=v),
    lambda ctx, v: Location(
        warehouse_id=ctx["warehouse"].id, code=f"L-{v}", type=LocationType.SHELF, capacity_units=v
    ),
    lambda ctx, v: Route(
        origin_warehouse_id=ctx["warehouse"].id,
        destination_warehouse_id=ctx["w2"].id,
        mode=TransportMode.TRUCK,
        distance_km=v,
    ),
]

FLOAT_FACTORIES = [
    lambda ctx, v: InventoryBalance(
        product_id=ctx["product"].id, location_id=ctx["dock"].id, on_hand=v
    ),
    lambda ctx, v: InventoryBalance(
        product_id=ctx["product"].id, location_id=ctx["dock"].id, reserved=v
    ),
    lambda ctx, v: OrderLine(
        order_id=ctx["order"].id, product_id=ctx["product"].id, qty_ordered=1, qty_allocated=v
    ),
    lambda ctx, v: OrderLine(
        order_id=ctx["order"].id, product_id=ctx["product"].id, qty_ordered=1, qty_shipped=v
    ),
    lambda ctx, v: OrderLine(
        order_id=ctx["order"].id,
        product_id=ctx["product"].id,
        qty_ordered=1,
        service_level_penalty=v,
    ),
    lambda ctx, v: POLine(
        purchase_order_id=ctx["po"].id, product_id=ctx["product"].id, qty_ordered=1, qty_received=v
    ),
    lambda ctx, v: InventoryMove(
        product_id=ctx["product"].id,
        move_type=MoveType.ADJUSTMENT,
        qty=1,
        occurred_at=datetime.now(UTC),
        reported_qty=v,
    ),
    lambda ctx, v: InventoryMove(
        product_id=ctx["product"].id,
        move_type=MoveType.ADJUSTMENT,
        qty=1,
        occurred_at=datetime.now(UTC),
        actual_qty=v,
    ),
    lambda ctx, v: LeadtimeModel(
        scope=LeadtimeScope.SUPPLIER, dist_family=DistFamily.NORMAL, rare_delay_add_days=v
    ),
    lambda ctx, v: SensorDevice(
        warehouse_id=ctx["warehouse"].id, device_type=DeviceType.CAMERA, noise_sigma=v
    ),
    lambda ctx, v: Observation(
        observed_at=datetime.now(UTC),
        device_id=ctx["device"].id,
        product_id=ctx["product"].id,
        location_id=ctx["dock"].id,
        obs_type=ObservationType.SCAN,
        observed_qty=v,
    ),
    lambda ctx, v: Observation(
        observed_at=datetime.now(UTC),
        device_id=ctx["device"].id,
        product_id=ctx["product"].id,
        location_id=ctx["dock"].id,
        obs_type=ObservationType.SCAN,
        reported_noise_sigma=v,
    ),
]


@pytest.mark.parametrize("invalid_value", [-1, -9999])
@pytest.mark.parametrize("factory_fn", INT_FACTORIES)
def test_non_negative_int_constraints(db_session, constraint_ctx, factory_fn, invalid_value):
    """Verifies that integer-based physical constraints correctly reject negative numbers."""
    obj = factory_fn(constraint_ctx, invalid_value)
    db_session.add(obj)

    with pytest.raises(IntegrityError):
        db_session.commit()


@pytest.mark.parametrize("invalid_value", [-1.0, -0.001, -9999.99])
@pytest.mark.parametrize("factory_fn", FLOAT_FACTORIES)
def test_non_negative_float_constraints(db_session, constraint_ctx, factory_fn, invalid_value):
    """Verifies that float-based physical constraints strictly
    reject even fractional negative values."""
    obj = factory_fn(constraint_ctx, invalid_value)
    db_session.add(obj)

    with pytest.raises(IntegrityError):
        db_session.commit()


@pytest.mark.parametrize(
    "factory_fn",
    [
        lambda w, p, ctx, v: OrderLine(order_id=ctx["order"].id, product_id=p.id, qty_ordered=v),
        lambda w, p, ctx, v: POLine(purchase_order_id=ctx["po"].id, product_id=p.id, qty_ordered=v),
        lambda w, p, ctx, v: InventoryMove(
            product_id=p.id,
            move_type=MoveType.ADJUSTMENT,
            qty=v,
            occurred_at=datetime.now(UTC),
        ),
    ],
)
@pytest.mark.parametrize("invalid_value", [0, -1.5])
def test_positive_constraints(db_session, seed_base_world, factory_fn, invalid_value):
    """
    Test that action-driven fields (orders, moves) strictly require a value > 0.

    Why this is important: Unlike balances (which can be 0), ordering or moving
    0 items is an invalid operation that creates empty transactional noise
    and breaks division logic in supply chain forecasting.
    """
    w = seed_base_world["warehouse"]
    p = seed_base_world["product"]
    sup = seed_base_world["supplier"]

    order = Order(customer_name="A")
    db_session.add(order)
    po = PurchaseOrder(supplier_id=sup.id, destination_warehouse_id=w.id)
    db_session.add(po)
    db_session.flush()

    ctx = {"order": order, "po": po}

    obj = factory_fn(w, p, ctx, invalid_value)
    db_session.add(obj)
    with pytest.raises(IntegrityError):
        db_session.commit()
