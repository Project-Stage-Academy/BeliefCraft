import uuid
import enum
from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    String,
    Integer,
    Float,
    Boolean,
    ForeignKey,
    CheckConstraint,
    DateTime,
    func,
    Enum as SAEnum
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship
)
from sqlalchemy.dialects.postgresql import UUID

# --- Enums ---

class QualityStatus(str, enum.Enum):
    OK = 'ok'
    DAMAGED = 'damaged'
    EXPIRED = 'expired'
    QUARANTINE = 'quarantine'

class MoveType(str, enum.Enum):
    INBOUND = 'inbound'
    OUTBOUND = 'outbound'
    TRANSFER = 'transfer'
    ADJUSTMENT = 'adjustment'

class LocationType(str, enum.Enum):
    SHELF = 'shelf'
    BIN = 'bin'
    PALLET_POS = 'pallet_pos'
    DOCK = 'dock'
    VIRTUAL = 'virtual'

class OrderStatus(str, enum.Enum):
    NEW = 'new'
    ALLOCATED = 'allocated'
    PICKED = 'picked'
    SHIPPED = 'shipped'
    CANCELLED = 'cancelled'

class POStatus(str, enum.Enum):
    DRAFT = 'draft'
    SUBMITTED = 'submitted'
    PARTIAL = 'partial'
    RECEIVED = 'received'
    CLOSED = 'closed'

class DeviceType(str, enum.Enum):
    CAMERA = 'camera'
    RFID_READER = 'rfid_reader'
    WEIGHT_SENSOR = 'weight_sensor'
    SCANNER = 'scanner'

class DeviceStatus(str, enum.Enum):
    ACTIVE = 'active'
    OFFLINE = 'offline'
    MAINTENANCE = 'maintenance'

class ShipmentStatus(str, enum.Enum):
    PLANNED = 'planned'
    IN_TRANSIT = 'in_transit'
    DELIVERED = 'delivered'
    EXCEPTION = 'exception'

class ShipmentDirection(str, enum.Enum):
    INBOUND = 'inbound'
    OUTBOUND = 'outbound'
    TRANSFER = 'transfer'

class TransportMode(str, enum.Enum):
    TRUCK = 'truck'
    AIR = 'air'
    RAIL = 'rail'
    SEA = 'sea'

class LeadtimeScope(str, enum.Enum):
    SUPPLIER = 'supplier'
    ROUTE = 'route'
    GLOBAL = 'global'

class DistFamily(str, enum.Enum):
    NORMAL = 'normal'
    LOGNORMAL = 'lognormal'
    POISSON = 'poisson'

class ObservationType(str, enum.Enum):
    SCAN = 'scan'
    IMAGE_RECOG = 'image_recog'
    MANUAL_COUNT = 'manual_count'

# --- Base ---

class Base(DeclarativeBase):
    pass

# --- Models ---

class Product(Base):
    __tablename__ = 'products'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    sku: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    shelf_life_days: Mapped[Optional[int]] = mapped_column(Integer, CheckConstraint('shelf_life_days >= 0'))

    # Relationships
    inventory_balances: Mapped[List["InventoryBalance"]] = relationship(back_populates="product")
    inventory_moves: Mapped[List["InventoryMove"]] = relationship(back_populates="product")
    order_lines: Mapped[List["OrderLine"]] = relationship(back_populates="product")
    po_lines: Mapped[List["POLine"]] = relationship(back_populates="product")

class Warehouse(Base):
    __tablename__ = 'warehouses'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    region: Mapped[str] = mapped_column(String, nullable=False)
    tz: Mapped[str] = mapped_column(String, nullable=False)

    # Relationships
    locations: Mapped[List["Location"]] = relationship(back_populates="warehouse")
    sensor_devices: Mapped[List["SensorDevice"]] = relationship(back_populates="warehouse")
    
    # Routes
    routes_origin: Mapped[List["Route"]] = relationship("Route", foreign_keys="[Route.origin_warehouse_id]", back_populates="origin_warehouse")
    routes_destination: Mapped[List["Route"]] = relationship("Route", foreign_keys="[Route.destination_warehouse_id]", back_populates="destination_warehouse")
    
    # Shipments
    shipments_origin: Mapped[List["Shipment"]] = relationship("Shipment", foreign_keys="[Shipment.origin_warehouse_id]", back_populates="origin_warehouse")
    shipments_destination: Mapped[List["Shipment"]] = relationship("Shipment", foreign_keys="[Shipment.destination_warehouse_id]", back_populates="destination_warehouse")

class Supplier(Base):
    __tablename__ = 'suppliers'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    reliability_score: Mapped[float] = mapped_column(Float, CheckConstraint('reliability_score >= 0 AND reliability_score <= 1'), default=0.5)
    region: Mapped[str] = mapped_column(String, nullable=False)

    # Relationships
    purchase_orders: Mapped[List["PurchaseOrder"]] = relationship(back_populates="supplier")

class LeadtimeModel(Base):
    __tablename__ = 'leadtime_models'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    scope: Mapped[LeadtimeScope] = mapped_column(SAEnum(LeadtimeScope, name='leadtime_scope'), nullable=False)
    dist_family: Mapped[DistFamily] = mapped_column(SAEnum(DistFamily, name='dist_family'), nullable=False)
    p1: Mapped[Optional[float]] = mapped_column(Float)
    p2: Mapped[Optional[float]] = mapped_column(Float)
    p_rare_delay: Mapped[float] = mapped_column(Float, CheckConstraint('p_rare_delay >= 0 AND p_rare_delay <= 1'), default=0)
    rare_delay_add_days: Mapped[float] = mapped_column(Float, CheckConstraint('rare_delay_add_days >= 0'), default=0)
    fitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Location(Base):
    __tablename__ = 'locations'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    warehouse_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('warehouses.id'), nullable=False)
    parent_location_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey('locations.id'))
    code: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[LocationType] = mapped_column(SAEnum(LocationType, name='location_type'), nullable=False)
    capacity_units: Mapped[int] = mapped_column(Integer, CheckConstraint('capacity_units >= 0'), nullable=False)

    # Relationships
    warehouse: Mapped["Warehouse"] = relationship(back_populates="locations")
    parent: Mapped[Optional["Location"]] = relationship("Location", remote_side=[id], back_populates="children")
    children: Mapped[List["Location"]] = relationship("Location", back_populates="parent")
    inventory_balances: Mapped[List["InventoryBalance"]] = relationship(back_populates="location")

class InventoryBalance(Base):
    __tablename__ = 'inventory_balances'
    __table_args__ = (
        CheckConstraint('on_hand >= 0', name='check_on_hand_positive'),
        CheckConstraint('reserved >= 0', name='check_reserved_positive'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('products.id'), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('locations.id'), nullable=False)
    on_hand: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    reserved: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    last_count_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    quality_status: Mapped[QualityStatus] = mapped_column(SAEnum(QualityStatus, name='quality_status'), default=QualityStatus.OK, nullable=False)

    # Relationships
    product: Mapped["Product"] = relationship(back_populates="inventory_balances")
    location: Mapped["Location"] = relationship(back_populates="inventory_balances")

class InventoryMove(Base):
    __tablename__ = 'inventory_moves'
    __table_args__ = (
        CheckConstraint('qty > 0', name='check_qty_positive'),
        CheckConstraint('reported_qty >= 0', name='check_reported_qty_positive'),
        CheckConstraint('actual_qty >= 0', name='check_actual_qty_positive'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('products.id'), nullable=False)
    from_location_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey('locations.id'))
    to_location_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey('locations.id'))
    move_type: Mapped[MoveType] = mapped_column(SAEnum(MoveType, name='move_type'), nullable=False)
    qty: Mapped[float] = mapped_column(Float, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason_code: Mapped[Optional[str]] = mapped_column(String)
    reported_qty: Mapped[Optional[float]] = mapped_column(Float)
    actual_qty: Mapped[Optional[float]] = mapped_column(Float)

    # Relationships
    product: Mapped["Product"] = relationship(back_populates="inventory_moves")
    from_location: Mapped[Optional["Location"]] = relationship("Location", foreign_keys=[from_location_id])
    to_location: Mapped[Optional["Location"]] = relationship("Location", foreign_keys=[to_location_id])
    observations: Mapped[List["Observation"]] = relationship(back_populates="related_move")

class SensorDevice(Base):
    __tablename__ = 'sensor_devices'
    __table_args__ = (
        CheckConstraint('noise_sigma >= 0', name='check_noise_positive'),
        CheckConstraint('missing_rate >= 0 AND missing_rate <= 1', name='check_missing_rate_valid'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    warehouse_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('warehouses.id'), nullable=False)
    device_type: Mapped[DeviceType] = mapped_column(SAEnum(DeviceType, name='device_type'), nullable=False)
    noise_sigma: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    missing_rate: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    bias: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    status: Mapped[DeviceStatus] = mapped_column(SAEnum(DeviceStatus, name='device_status'), default=DeviceStatus.ACTIVE, nullable=False)

    # Relationships
    warehouse: Mapped["Warehouse"] = relationship(back_populates="sensor_devices")
    observations: Mapped[List["Observation"]] = relationship(back_populates="device")

class Route(Base):
    __tablename__ = 'routes'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    origin_warehouse_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('warehouses.id'), nullable=False)
    destination_warehouse_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('warehouses.id'), nullable=False)
    mode: Mapped[TransportMode] = mapped_column(SAEnum(TransportMode, name='route_mode'), nullable=False)
    distance_km: Mapped[float] = mapped_column(Float, CheckConstraint('distance_km >= 0'), nullable=False)
    leadtime_model_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey('leadtime_models.id'))

    # Relationships
    origin_warehouse: Mapped["Warehouse"] = relationship("Warehouse", foreign_keys=[origin_warehouse_id], back_populates="routes_origin")
    destination_warehouse: Mapped["Warehouse"] = relationship("Warehouse", foreign_keys=[destination_warehouse_id], back_populates="routes_destination")
    leadtime_model: Mapped[Optional["LeadtimeModel"]] = relationship("LeadtimeModel")

class Order(Base):
    __tablename__ = 'orders'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    customer_name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[OrderStatus] = mapped_column(SAEnum(OrderStatus, name='order_status'), default=OrderStatus.NEW, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    promised_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    sla_priority: Mapped[float] = mapped_column(Float, CheckConstraint('sla_priority >= 0 AND sla_priority <= 1'), default=0.5, nullable=False)
    requested_ship_from_region: Mapped[Optional[str]] = mapped_column(String)

    # Relationships
    lines: Mapped[List["OrderLine"]] = relationship(back_populates="order")
    shipments: Mapped[List["Shipment"]] = relationship(back_populates="order")

class OrderLine(Base):
    __tablename__ = 'order_lines'
    __table_args__ = (
        CheckConstraint('qty_ordered > 0', name='check_qty_ordered_pos'),
        CheckConstraint('qty_allocated >= 0', name='check_qty_allocated_pos'),
        CheckConstraint('qty_shipped >= 0', name='check_qty_shipped_pos'),
        CheckConstraint('service_level_penalty >= 0', name='check_penalty_pos'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('orders.id'), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('products.id'), nullable=False)
    qty_ordered: Mapped[float] = mapped_column(Float, nullable=False)
    qty_allocated: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    qty_shipped: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    service_level_penalty: Mapped[float] = mapped_column(Float, default=0, nullable=False)

    # Relationships
    order: Mapped["Order"] = relationship(back_populates="lines")
    product: Mapped["Product"] = relationship(back_populates="order_lines")

class PurchaseOrder(Base):
    __tablename__ = 'purchase_orders'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('suppliers.id'), nullable=False)
    destination_warehouse_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('warehouses.id'), nullable=False)
    status: Mapped[POStatus] = mapped_column(SAEnum(POStatus, name='po_status'), default=POStatus.DRAFT, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    leadtime_model_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey('leadtime_models.id'))

    # Relationships
    supplier: Mapped["Supplier"] = relationship(back_populates="purchase_orders")
    destination_warehouse: Mapped["Warehouse"] = relationship("Warehouse")
    leadtime_model: Mapped[Optional["LeadtimeModel"]] = relationship("LeadtimeModel")
    lines: Mapped[List["POLine"]] = relationship(back_populates="purchase_order")
    shipments: Mapped[List["Shipment"]] = relationship(back_populates="purchase_order")

class POLine(Base):
    __tablename__ = 'po_lines'
    __table_args__ = (
        CheckConstraint('qty_ordered > 0', name='check_po_qty_ordered_pos'),
        CheckConstraint('qty_received >= 0', name='check_po_qty_received_pos'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('purchase_orders.id'), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('products.id'), nullable=False)
    qty_ordered: Mapped[float] = mapped_column(Float, nullable=False)
    qty_received: Mapped[float] = mapped_column(Float, default=0, nullable=False)

    # Relationships
    purchase_order: Mapped["PurchaseOrder"] = relationship(back_populates="lines")
    product: Mapped["Product"] = relationship(back_populates="po_lines")

class Shipment(Base):
    __tablename__ = 'shipments'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    direction: Mapped[ShipmentDirection] = mapped_column(SAEnum(ShipmentDirection, name='shipment_direction'), nullable=False)
    origin_warehouse_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey('warehouses.id'))
    destination_warehouse_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey('warehouses.id'))
    order_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey('orders.id'))
    purchase_order_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey('purchase_orders.id'))
    route_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey('routes.id'))
    status: Mapped[ShipmentStatus] = mapped_column(SAEnum(ShipmentStatus, name='shipment_status'), default=ShipmentStatus.PLANNED, nullable=False)
    shipped_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    arrived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relationships
    origin_warehouse: Mapped[Optional["Warehouse"]] = relationship("Warehouse", foreign_keys=[origin_warehouse_id], back_populates="shipments_origin")
    destination_warehouse: Mapped[Optional["Warehouse"]] = relationship("Warehouse", foreign_keys=[destination_warehouse_id], back_populates="shipments_destination")
    order: Mapped[Optional["Order"]] = relationship(back_populates="shipments")
    purchase_order: Mapped[Optional["PurchaseOrder"]] = relationship(back_populates="shipments")
    route: Mapped[Optional["Route"]] = relationship("Route")
    observations: Mapped[List["Observation"]] = relationship(back_populates="related_shipment")

class Observation(Base):
    __tablename__ = 'observations'
    __table_args__ = (
        CheckConstraint('observed_qty >= 0', name='check_obs_qty_pos'),
        CheckConstraint('confidence >= 0 AND confidence <= 1', name='check_confidence_valid'),
        CheckConstraint('reported_noise_sigma >= 0', name='check_noise_sigma_pos'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('sensor_devices.id'), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('products.id'), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('locations.id'), nullable=False)
    obs_type: Mapped[ObservationType] = mapped_column(SAEnum(ObservationType, name='obs_type'), nullable=False)
    observed_qty: Mapped[Optional[float]] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    is_missing: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reported_noise_sigma: Mapped[Optional[float]] = mapped_column(Float)
    related_move_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey('inventory_moves.id'))
    related_shipment_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey('shipments.id'))

    # Relationships
    device: Mapped["SensorDevice"] = relationship(back_populates="observations")
    product: Mapped["Product"] = relationship("Product")
    location: Mapped["Location"] = relationship("Location")
    related_move: Mapped[Optional["InventoryMove"]] = relationship(back_populates="observations")
    related_shipment: Mapped[Optional["Shipment"]] = relationship(back_populates="observations")