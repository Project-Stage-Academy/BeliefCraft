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
from packages.database.src.constraints import check_between_zero_one, check_non_negative
from packages.database.src.enums import (
    ShipmentStatus,
    ShipmentDirection,
    TransportMode,
    LeadtimeScope,
    DistFamily,
)


class Warehouse(Base):
    __tablename__ = "warehouses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    region: Mapped[str] = mapped_column(String, nullable=False)
    tz: Mapped[str] = mapped_column(String, nullable=False)

    # Relationships
    locations: Mapped[List["Location"]] = relationship(back_populates="warehouse")
    sensor_devices: Mapped[List["SensorDevice"]] = relationship(back_populates="warehouse")

    # Routes
    routes_origin: Mapped[List["Route"]] = relationship(
        "Route",
        foreign_keys="[Route.origin_warehouse_id]",
        back_populates="origin_warehouse",
    )
    routes_destination: Mapped[List["Route"]] = relationship(
        "Route",
        foreign_keys="[Route.destination_warehouse_id]",
        back_populates="destination_warehouse",
    )

    # Shipments
    shipments_origin: Mapped[List["Shipment"]] = relationship(
        "Shipment",
        foreign_keys="[Shipment.origin_warehouse_id]",
        back_populates="origin_warehouse",
    )
    shipments_destination: Mapped[List["Shipment"]] = relationship(
        "Shipment",
        foreign_keys="[Shipment.destination_warehouse_id]",
        back_populates="destination_warehouse",
    )


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    reliability_score: Mapped[float] = mapped_column(
        Float,
        check_between_zero_one("reliability_score"),
        default=0.5,
    )
    region: Mapped[str] = mapped_column(String, nullable=False)

    # Relationships
    purchase_orders: Mapped[List["PurchaseOrder"]] = relationship(back_populates="supplier")


class LeadtimeModel(Base):
    __tablename__ = "leadtime_models"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    scope: Mapped[LeadtimeScope] = mapped_column(
        SAEnum(LeadtimeScope, name="leadtime_scope"),
        nullable=False,
    )
    dist_family: Mapped[DistFamily] = mapped_column(
        SAEnum(DistFamily, name="dist_family"),
        nullable=False,
    )
    p1: Mapped[Optional[float]] = mapped_column(Float)
    p2: Mapped[Optional[float]] = mapped_column(Float)
    p_rare_delay: Mapped[float] = mapped_column(
        Float,
        check_between_zero_one("p_rare_delay"),
        default=0,
    )
    rare_delay_add_days: Mapped[float] = mapped_column(
        Float,
        check_non_negative("rare_delay_add_days"),
        default=0,
    )
    fitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class Route(Base):
    __tablename__ = "routes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    origin_warehouse_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("warehouses.id"),
        nullable=False,
    )
    destination_warehouse_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("warehouses.id"),
        nullable=False,
    )
    mode: Mapped[TransportMode] = mapped_column(
        SAEnum(TransportMode, name="route_mode"),
        nullable=False,
    )
    distance_km: Mapped[float] = mapped_column(
        Float,
        check_non_negative("distance_km"),
        nullable=False,
    )
    leadtime_model_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("leadtime_models.id")
    )

    # Relationships
    origin_warehouse: Mapped["Warehouse"] = relationship(
        "Warehouse",
        foreign_keys=[origin_warehouse_id],
        back_populates="routes_origin",
    )
    destination_warehouse: Mapped["Warehouse"] = relationship(
        "Warehouse",
        foreign_keys=[destination_warehouse_id],
        back_populates="routes_destination",
    )
    leadtime_model: Mapped[Optional["LeadtimeModel"]] = relationship("LeadtimeModel")


class Shipment(Base):
    __tablename__ = "shipments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    direction: Mapped[ShipmentDirection] = mapped_column(
        SAEnum(ShipmentDirection, name="shipment_direction"),
        nullable=False,
    )
    origin_warehouse_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("warehouses.id"))
    destination_warehouse_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("warehouses.id")
    )
    order_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("orders.id"))
    purchase_order_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("purchase_orders.id")
    )
    route_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("routes.id"))
    status: Mapped[ShipmentStatus] = mapped_column(
        SAEnum(ShipmentStatus, name="shipment_status"),
        default=ShipmentStatus.PLANNED,
        nullable=False,
    )
    shipped_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    arrived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relationships
    origin_warehouse: Mapped[Optional["Warehouse"]] = relationship(
        "Warehouse",
        foreign_keys=[origin_warehouse_id],
        back_populates="shipments_origin",
    )
    destination_warehouse: Mapped[Optional["Warehouse"]] = relationship(
        "Warehouse",
        foreign_keys=[destination_warehouse_id],
        back_populates="shipments_destination",
    )
    order: Mapped[Optional["Order"]] = relationship(back_populates="shipments")
    purchase_order: Mapped[Optional["PurchaseOrder"]] = relationship(back_populates="shipments")
    route: Mapped[Optional["Route"]] = relationship("Route")
    observations: Mapped[List["Observation"]] = relationship(back_populates="related_shipment")
