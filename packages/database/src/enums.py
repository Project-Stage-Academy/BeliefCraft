import enum


class QualityStatus(str, enum.Enum):
    OK = "ok"
    DAMAGED = "damaged"
    EXPIRED = "expired"
    QUARANTINE = "quarantine"


class MoveType(str, enum.Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    TRANSFER = "transfer"
    ADJUSTMENT = "adjustment"


class LocationType(str, enum.Enum):
    SHELF = "shelf"
    BIN = "bin"
    PALLET_POS = "pallet_pos"
    DOCK = "dock"
    VIRTUAL = "virtual"


class OrderStatus(str, enum.Enum):
    NEW = "new"
    ALLOCATED = "allocated"
    PICKED = "picked"
    SHIPPED = "shipped"
    CANCELLED = "cancelled"


class POStatus(str, enum.Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    PARTIAL = "partial"
    RECEIVED = "received"
    CLOSED = "closed"


class DeviceType(str, enum.Enum):
    CAMERA = "camera"
    RFID_READER = "rfid_reader"
    WEIGHT_SENSOR = "weight_sensor"
    SCANNER = "scanner"


class DeviceStatus(str, enum.Enum):
    ACTIVE = "active"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"


class ShipmentStatus(str, enum.Enum):
    PLANNED = "planned"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    EXCEPTION = "exception"


class ShipmentDirection(str, enum.Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    TRANSFER = "transfer"


class TransportMode(str, enum.Enum):
    TRUCK = "truck"
    AIR = "air"
    RAIL = "rail"
    SEA = "sea"


class LeadtimeScope(str, enum.Enum):
    SUPPLIER = "supplier"
    ROUTE = "route"
    GLOBAL = "global"


class DistFamily(str, enum.Enum):
    NORMAL = "normal"
    LOGNORMAL = "lognormal"
    POISSON = "poisson"


class ObservationType(str, enum.Enum):
    SCAN = "scan"
    IMAGE_RECOG = "image_recog"
    MANUAL_COUNT = "manual_count"
