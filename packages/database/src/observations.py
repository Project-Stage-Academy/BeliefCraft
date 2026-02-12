import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy import (
    Float,
    ForeignKey,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from packages.database.src.base import Base
from packages.database.src.constraints import (
    check_between_zero_one,
    check_non_negative,
)
from packages.database.src.enums import DeviceStatus, DeviceType, ObservationType

if TYPE_CHECKING:
    from packages.database.src.inventory import InventoryMove, Location, Product
    from packages.database.src.logistics import Shipment, Warehouse


class SensorDevice(Base):
    __tablename__ = "sensor_devices"
    __table_args__ = (
        check_non_negative("noise_sigma", name="check_noise_positive"),
        check_between_zero_one("missing_rate", name="check_missing_rate_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("warehouses.id"), nullable=False)
    device_type: Mapped[DeviceType] = mapped_column(
        SAEnum(DeviceType, name="device_type"),
        nullable=False,
    )
    noise_sigma: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    missing_rate: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    bias: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    status: Mapped[DeviceStatus] = mapped_column(
        SAEnum(DeviceStatus, name="device_status"),
        default=DeviceStatus.ACTIVE,
        nullable=False,
    )

    # Relationships
    warehouse: Mapped["Warehouse"] = relationship(back_populates="sensor_devices")
    observations: Mapped[list["Observation"]] = relationship(back_populates="device")


class Observation(Base):
    __tablename__ = "observations"
    __table_args__ = (
        check_non_negative("observed_qty", name="check_obs_qty_pos"),
        check_between_zero_one("confidence", name="check_confidence_valid"),
        check_non_negative("reported_noise_sigma", name="check_noise_sigma_pos"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sensor_devices.id"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locations.id"), nullable=False)
    obs_type: Mapped[ObservationType] = mapped_column(
        SAEnum(ObservationType, name="obs_type"),
        nullable=False,
    )
    observed_qty: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    is_missing: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reported_noise_sigma: Mapped[float | None] = mapped_column(Float)
    related_move_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("inventory_moves.id"))
    related_shipment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("shipments.id"))

    # Relationships
    device: Mapped["SensorDevice"] = relationship(back_populates="observations")
    product: Mapped["Product"] = relationship("Product")
    location: Mapped["Location"] = relationship("Location")
    related_move: Mapped[Optional["InventoryMove"]] = relationship(back_populates="observations")
    related_shipment: Mapped[Optional["Shipment"]] = relationship(back_populates="observations")
