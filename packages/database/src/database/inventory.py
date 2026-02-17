import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from database.base import Base
from database.constraints import check_non_negative, check_positive
from database.enums import LocationType, MoveType, QualityStatus
from sqlalchemy import (
    DateTime,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy import (
    Float,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from database.logistics import Warehouse
    from database.observations import Observation
    from database.orders import OrderLine, POLine


class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    sku: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    shelf_life_days: Mapped[int | None] = mapped_column(
        Integer,
        check_non_negative("shelf_life_days"),
    )

    # Relationships
    inventory_balances: Mapped[list["InventoryBalance"]] = relationship(back_populates="product")
    inventory_moves: Mapped[list["InventoryMove"]] = relationship(back_populates="product")
    order_lines: Mapped[list["OrderLine"]] = relationship(back_populates="product")
    po_lines: Mapped[list["POLine"]] = relationship(back_populates="product")


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("warehouses.id"), nullable=False)
    parent_location_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("locations.id"))
    code: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[LocationType] = mapped_column(
        SAEnum(LocationType, name="location_type"),
        nullable=False,
    )
    capacity_units: Mapped[int] = mapped_column(
        Integer,
        check_non_negative("capacity_units"),
        nullable=False,
    )

    # Relationships
    warehouse: Mapped["Warehouse"] = relationship(back_populates="locations")
    parent: Mapped[Optional["Location"]] = relationship(
        "Location",
        remote_side=[id],
        back_populates="children",
    )
    children: Mapped[list["Location"]] = relationship("Location", back_populates="parent")
    inventory_balances: Mapped[list["InventoryBalance"]] = relationship(back_populates="location")


class InventoryBalance(Base):
    __tablename__ = "inventory_balances"
    __table_args__ = (
        check_non_negative("on_hand", name="check_on_hand_positive"),
        check_non_negative("reserved", name="check_reserved_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locations.id"), nullable=False)
    on_hand: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    reserved: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    last_count_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quality_status: Mapped[QualityStatus] = mapped_column(
        SAEnum(QualityStatus, name="quality_status"),
        default=QualityStatus.OK,
        nullable=False,
    )

    # Relationships
    product: Mapped["Product"] = relationship(back_populates="inventory_balances")
    location: Mapped["Location"] = relationship(back_populates="inventory_balances")


class InventoryMove(Base):
    __tablename__ = "inventory_moves"
    __table_args__ = (
        check_positive("qty", name="check_qty_positive"),
        check_non_negative("reported_qty", name="check_reported_qty_positive"),
        check_non_negative("actual_qty", name="check_actual_qty_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), nullable=False)
    from_location_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("locations.id"))
    to_location_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("locations.id"))
    move_type: Mapped[MoveType] = mapped_column(
        SAEnum(MoveType, name="move_type"),
        nullable=False,
    )
    qty: Mapped[float] = mapped_column(Float, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String)
    reported_qty: Mapped[float | None] = mapped_column(Float)
    actual_qty: Mapped[float | None] = mapped_column(Float)

    # Relationships
    product: Mapped["Product"] = relationship(back_populates="inventory_moves")
    from_location: Mapped[Optional["Location"]] = relationship(
        "Location",
        foreign_keys=[from_location_id],
    )
    to_location: Mapped[Optional["Location"]] = relationship(
        "Location",
        foreign_keys=[to_location_id],
    )
    observations: Mapped[list["Observation"]] = relationship(back_populates="related_move")
