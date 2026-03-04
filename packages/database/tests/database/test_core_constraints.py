import uuid

import pytest
from database.enums import LocationType
from database.inventory import Location, Product
from database.logistics import Supplier, Warehouse
from sqlalchemy.exc import IntegrityError


def test_primary_key_uuid_generation(db_session):
    """
    Verify that primary keys auto-generate valid v4 UUIDs on insert.

    Why this is important: Ensures the database default `gen_random_uuid()`
    is correctly bound to the `id` column, preventing manual ID assignment
    errors and guaranteeing global uniqueness.
    """
    product = Product(sku="UUID-TEST", name="Test", category="Test")
    db_session.add(product)
    db_session.flush()
    assert isinstance(product.id, uuid.UUID)


@pytest.mark.parametrize(
    "model_cls, kwargs",
    [
        (Product, {"sku": "DUPE", "name": "A", "category": "A"}),
        (Warehouse, {"name": "DUPE", "region": "A", "tz": "UTC"}),
        (Supplier, {"name": "DUPE", "region": "A"}),
    ],
)
def test_unique_constraints(db_session, model_cls, kwargs):
    """
    Validate that UNIQUE constraints reject duplicate entries.

    Why this is important: Prevents logical data corruption, such as two
    warehouses or products sharing the same exact identifier, which would
    break inventory aggregation and routing logic.
    """
    db_session.add(model_cls(**kwargs))
    db_session.commit()

    db_session.add(model_cls(**kwargs))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_foreign_key_constraint(db_session):
    """
    Ensure foreign key constraints strictly enforce referential integrity.

    Why this is important: Database-level FKs act as the final defense
    against orphaned records (e.g., placing inventory in a warehouse
    that does not exist), overriding any application-level bugs.
    """
    location = Location(
        warehouse_id=uuid.uuid4(),
        code="LOC-1",
        type=LocationType.SHELF,
        capacity_units=100,
    )
    db_session.add(location)
    with pytest.raises(IntegrityError):
        db_session.commit()
