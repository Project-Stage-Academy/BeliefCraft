import enum


class QualityStatus(enum.StrEnum):
    OK = "ok"
    DAMAGED = "damaged"
    EXPIRED = "expired"
    QUARANTINE = "quarantine"


class MoveType(enum.StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    TRANSFER = "transfer"
    ADJUSTMENT = "adjustment"


class LocationType(enum.StrEnum):
    SHELF = "shelf"
    BIN = "bin"
    PALLET_POS = "pallet_pos"
    DOCK = "dock"
    VIRTUAL = "virtual"


class OrderStatus(enum.StrEnum):
    NEW = "new"
    ALLOCATED = "allocated"
    PICKED = "picked"
    SHIPPED = "shipped"
    CANCELLED = "cancelled"


class POStatus(enum.StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    PARTIAL = "partial"
    RECEIVED = "received"
    CLOSED = "closed"


class DeviceType(enum.StrEnum):
    CAMERA = "camera"
    RFID_READER = "rfid_reader"
    WEIGHT_SENSOR = "weight_sensor"
    SCANNER = "scanner"


class DeviceStatus(enum.StrEnum):
    ACTIVE = "active"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"


class ShipmentStatus(enum.StrEnum):
    PLANNED = "planned"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    EXCEPTION = "exception"


class ShipmentDirection(enum.StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    TRANSFER = "transfer"


class TransportMode(enum.StrEnum):
    TRUCK = "truck"
    AIR = "air"
    RAIL = "rail"
    SEA = "sea"


class LeadtimeScope(enum.StrEnum):
    SUPPLIER = "supplier"
    ROUTE = "route"
    GLOBAL = "global"


class DistFamily(enum.StrEnum):
    NORMAL = "normal"
    LOGNORMAL = "lognormal"
    POISSON = "poisson"


class ObservationType(enum.StrEnum):
    SCAN = "scan"
    IMAGE_RECOG = "image_recog"
    MANUAL_COUNT = "manual_count"
