from pydantic import BaseModel, ConfigDict, Field


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
