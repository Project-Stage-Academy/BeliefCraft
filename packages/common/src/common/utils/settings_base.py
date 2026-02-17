from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class BaseSettings(BaseModel):
    """
    Shared root settings model for service configuration schemas.
    Service-specific settings classes should inherit from this class.
    """

    model_config = ConfigDict(extra="forbid")
