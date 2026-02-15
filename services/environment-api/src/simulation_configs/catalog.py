from pydantic import BaseModel, ConfigDict, Field


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
