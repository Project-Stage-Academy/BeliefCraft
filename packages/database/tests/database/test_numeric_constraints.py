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


@pytest.mark.parametrize(
    "factory_fn",
    [
        lambda w, p, ctx, v: Product(sku=f"P-{v}", name="A", category="A", shelf_life_days=v),
        lambda w, p, ctx, v: Location(
            warehouse_id=w.id, code=f"L-{v}", type=LocationType.SHELF, capacity_units=v
        ),
        lambda w, p, ctx, v: InventoryBalance(
            product_id=p.id, location_id=ctx["dock"].id, on_hand=v
        ),
        lambda w, p, ctx, v: InventoryBalance(
            product_id=p.id, location_id=ctx["dock"].id, reserved=v
        ),
        lambda w, p, ctx, v: OrderLine(
            order_id=ctx["order"].id, product_id=p.id, qty_ordered=1, qty_allocated=v
        ),
        lambda w, p, ctx, v: OrderLine(
            order_id=ctx["order"].id, product_id=p.id, qty_ordered=1, qty_shipped=v
        ),
        lambda w, p, ctx, v: OrderLine(
            order_id=ctx["order"].id, product_id=p.id, qty_ordered=1, service_level_penalty=v
        ),
        lambda w, p, ctx, v: POLine(
            purchase_order_id=ctx["po"].id, product_id=p.id, qty_ordered=1, qty_received=v
        ),
        lambda w, p, ctx, v: InventoryMove(
            product_id=p.id,
            move_type=MoveType.ADJUSTMENT,
            qty=1,
            occurred_at=datetime.now(UTC),
            reported_qty=v,
        ),
        lambda w, p, ctx, v: InventoryMove(
            product_id=p.id,
            move_type=MoveType.ADJUSTMENT,
            qty=1,
            occurred_at=datetime.now(UTC),
            actual_qty=v,
        ),
        lambda w, p, ctx, v: Route(
            origin_warehouse_id=w.id,
            destination_warehouse_id=ctx["w2"].id,
            mode=TransportMode.TRUCK,
            distance_km=v,
        ),
        lambda w, p, ctx, v: LeadtimeModel(
            scope=LeadtimeScope.SUPPLIER, dist_family=DistFamily.NORMAL, rare_delay_add_days=v
        ),
        lambda w, p, ctx, v: SensorDevice(
            warehouse_id=w.id, device_type=DeviceType.CAMERA, noise_sigma=v
        ),
        lambda w, p, ctx, v: Observation(
            observed_at=datetime.now(UTC),
            device_id=ctx["device"].id,
            product_id=p.id,
            location_id=ctx["dock"].id,
            obs_type=ObservationType.SCAN,
            observed_qty=v,
        ),
        lambda w, p, ctx, v: Observation(
            observed_at=datetime.now(UTC),
            device_id=ctx["device"].id,
            product_id=p.id,
            location_id=ctx["dock"].id,
            obs_type=ObservationType.SCAN,
            reported_noise_sigma=v,
        ),
    ],
)
def test_non_negative_constraints(db_session, seed_base_world, factory_fn):
    """
    Test that fields representing physical bounds or capacities reject negative values.

    Why this is important: Negative distances, capacities, or inventory balances
    are physically impossible. Allowing them would cause silent mathematical
    failures in routing algorithms and financial reporting.
    """
    w = seed_base_world["warehouse"]
    p = seed_base_world["product"]
    dock = seed_base_world["dock"]
    sup = seed_base_world["supplier"]

    w2 = Warehouse(name="W2", region="A", tz="UTC")
    db_session.add(w2)
    order = Order(customer_name="A")
    db_session.add(order)
    po = PurchaseOrder(supplier_id=sup.id, destination_warehouse_id=w.id)
    db_session.add(po)
    dev = SensorDevice(warehouse_id=w.id, device_type=DeviceType.CAMERA)
    db_session.add(dev)
    db_session.flush()

    ctx = {"dock": dock, "w2": w2, "order": order, "po": po, "device": dev}

    obj = factory_fn(w, p, ctx, -1.0)
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
