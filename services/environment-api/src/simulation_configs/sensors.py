from pydantic import BaseModel, ConfigDict, Field


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
