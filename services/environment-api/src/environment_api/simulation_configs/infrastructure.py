from pydantic import BaseModel, ConfigDict


class InfrastructureConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    region_timezones: dict[str, str]
