from pydantic import BaseModel, ConfigDict, Field


class OutboundConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active_catalog_fraction: float = Field(default=0.2, gt=0.0, le=1.0)
    poisson_mean: float = Field(default=2.0, gt=0.0)
    customer_names: list[str] = Field(min_length=1)
    missed_sale_penalty_per_unit: float = Field(default=10.0, ge=0.0)
