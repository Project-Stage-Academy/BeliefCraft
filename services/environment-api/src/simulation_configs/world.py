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
