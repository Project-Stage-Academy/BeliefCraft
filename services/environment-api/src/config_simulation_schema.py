from pydantic import BaseModel, ConfigDict, Field


class SimulationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_days: int = Field(default=365, gt=0)
    random_seed: int = Field(default=42)
    commit_interval: int = Field(default=10, gt=0)


class WorldConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    warehouse_count: int = Field(default=3, ge=1)
    product_count: int = Field(default=50, ge=1)
    supplier_count: int = Field(default=5, ge=1)


class ShelfLifeRange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_days: int = Field(ge=1)
    max_days: int = Field(ge=1)


class SupplierReliabilityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min: float = Field(default=0.7, ge=0.0, le=1.0)
    max: float = Field(default=0.99, ge=0.0, le=1.0)


class CatalogConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_shelf_life: dict[str, ShelfLifeRange]

    supplier_regions: list[str] = Field(
        default_factory=lambda: ["NA-EAST", "EU-WEST", "APAC-SG", "NA-WEST", "EU-CENTRAL"]
    )
    supplier_reliability: SupplierReliabilityConfig = Field(
        default_factory=SupplierReliabilityConfig
    )


class InfrastructureConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    region_timezones: dict[str, str]


class CapacityRangeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capacity_min: int = Field(ge=1)
    capacity_max: int = Field(ge=1)


class CountCapacityConfig(CapacityRangeConfig):
    model_config = ConfigDict(extra="forbid")
    count_min: int = Field(ge=1)
    count_max: int = Field(ge=1)


class SensorProfileConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    weight: float = Field(ge=0.0)
    noise_min: float = Field(ge=0.0, le=1.0)
    noise_max: float = Field(ge=0.0, le=1.0)
    missing_min: float = Field(ge=0.0, le=1.0)
    missing_max: float = Field(ge=0.0, le=1.0)


class SensorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attach_probability: float = Field(default=0.2, ge=0.0, le=1.0)
    camera: SensorProfileConfig
    rfid: SensorProfileConfig


class LayoutConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dock: CapacityRangeConfig
    zone: CountCapacityConfig
    aisle: CountCapacityConfig
    sensor: SensorConfig


class LeadtimeModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    p1: float = Field(ge=0.0)
    p2: float = Field(ge=0.0)
    p_rare_delay: float = Field(ge=0.0, le=1.0)
    rare_delay_add_days: float = Field(ge=0.0)


class LogisticsModelsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    express: LeadtimeModelConfig
    standard: LeadtimeModelConfig
    ocean: LeadtimeModelConfig


class DistanceRangeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min_km: int = Field(ge=1)
    max_km: int = Field(ge=1)


class RoutingThresholdsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    truck_max_km: int = Field(gt=0)
    air_max_km: int = Field(gt=0)


class LogisticsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    models: LogisticsModelsConfig
    distance: DistanceRangeConfig
    thresholds: RoutingThresholdsConfig


class OutboundConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active_catalog_fraction: float = Field(default=0.2, gt=0.0, le=1.0)
    poisson_mean: float = Field(default=2.0, gt=0.0)
    customer_names: list[str] = Field(min_length=1)
    missed_sale_penalty_per_unit: float = Field(default=10.0, ge=0.0)


class ReplenishmentPolicyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reorder_point: float = Field(ge=0.0)
    target_level: float = Field(gt=0.0)


class ReplenishmentLeadTimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mean_days: float = Field(gt=0.0)
    std_dev_days: float = Field(ge=0.0)
    min_days: int = Field(ge=1)


class ReplenishmentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_catalog_fraction: float = Field(default=0.10, gt=0.0, le=1.0)
    policy: ReplenishmentPolicyConfig
    lead_time: ReplenishmentLeadTimeConfig


class ScanProbabilityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dock: float = Field(default=0.90, ge=0.0, le=1.0)
    default: float = Field(default=0.05, ge=0.0, le=1.0)


class ObservationNoiseConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_sigma_units: float = Field(default=1.0, gt=0.0)
    noise_mean: float = Field(default=0.0)
    min_observed_qty: float = Field(default=0.0, ge=0.0)
    min_confidence: float = Field(default=0.1, ge=0.0, le=1.0)
    base_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    noise_multiplier: float = Field(default=10.0, ge=0.0)


class SensorsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scan_probabilities: ScanProbabilityConfig = Field(default_factory=ScanProbabilityConfig)
    noise_model: ObservationNoiseConfig = Field(default_factory=ObservationNoiseConfig)
