import uuid
from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    String,
    Float,
    ForeignKey,
    DateTime,
    func,
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from packages.database.src.base import Base
from packages.database.src.constraints import (
    check_between_zero_one,
    check_non_negative,
    check_positive,
)
from packages.database.src.enums import OrderStatus, POStatus
from packages.database.src.mixins import AuditTimestampMixin


class Order(AuditTimestampMixin, Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    customer_name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[OrderStatus] = mapped_column(
        SAEnum(OrderStatus, name="order_status"),
        default=OrderStatus.NEW,
        nullable=False,
    )
    promised_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    sla_priority: Mapped[float] = mapped_column(
        Float,
        check_between_zero_one("sla_priority"),
        default=0.5,
        nullable=False,
    )
    requested_ship_from_region: Mapped[Optional[str]] = mapped_column(String)

    # Relationships
    lines: Mapped[List["OrderLine"]] = relationship(back_populates="order")
    shipments: Mapped[List["Shipment"]] = relationship(back_populates="order")


class OrderLine(Base):
    __tablename__ = "order_lines"
    __table_args__ = (
        check_positive("qty_ordered", name="check_qty_ordered_pos"),
        check_non_negative("qty_allocated", name="check_qty_allocated_pos"),
        check_non_negative("qty_shipped", name="check_qty_shipped_pos"),
        check_non_negative("service_level_penalty", name="check_penalty_pos"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), nullable=False)
    qty_ordered: Mapped[float] = mapped_column(Float, nullable=False)
    qty_allocated: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    qty_shipped: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    service_level_penalty: Mapped[float] = mapped_column(Float, default=0, nullable=False)

    # Relationships
    order: Mapped["Order"] = relationship(back_populates="lines")
    product: Mapped["Product"] = relationship(back_populates="order_lines")


class PurchaseOrder(AuditTimestampMixin, Base):
    __tablename__ = "purchase_orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.id"), nullable=False)
    destination_warehouse_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("warehouses.id"),
        nullable=False,
    )
    status: Mapped[POStatus] = mapped_column(
        SAEnum(POStatus, name="po_status"),
        default=POStatus.DRAFT,
        nullable=False,
    )
    expected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    leadtime_model_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("leadtime_models.id")
    )

    # Relationships
    supplier: Mapped["Supplier"] = relationship(back_populates="purchase_orders")
    destination_warehouse: Mapped["Warehouse"] = relationship("Warehouse")
    leadtime_model: Mapped[Optional["LeadtimeModel"]] = relationship("LeadtimeModel")
    lines: Mapped[List["POLine"]] = relationship(back_populates="purchase_order")
    shipments: Mapped[List["Shipment"]] = relationship(back_populates="purchase_order")


class POLine(Base):
    __tablename__ = "po_lines"
    __table_args__ = (
        check_positive("qty_ordered", name="check_po_qty_ordered_pos"),
        check_non_negative("qty_received", name="check_po_qty_received_pos"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("purchase_orders.id"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), nullable=False)
    qty_ordered: Mapped[float] = mapped_column(Float, nullable=False)
    qty_received: Mapped[float] = mapped_column(Float, default=0, nullable=False)

    # Relationships
    purchase_order: Mapped["PurchaseOrder"] = relationship(back_populates="lines")
    product: Mapped["Product"] = relationship(back_populates="po_lines")
