from datetime import UTC, datetime

from app.config import Settings, get_settings
from app.services.health_checker import HealthChecker
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

router = APIRouter()
settings_dependency = Depends(get_settings)


class HealthResponse(BaseModel):
    """Health check response model"""

    status: str
    service: str
    version: str
    timestamp: str
    dependencies: dict[str, str]


@router.get("/health", response_model=HealthResponse)
async def health_check(
    request: Request,
    settings: Settings = settings_dependency,
) -> HealthResponse:
    """
    Health check endpoint - verifies service and dependencies

    Returns:
        HealthResponse with overall status and individual dependency statuses
    """
    checker = HealthChecker(settings, request.app.state.redis_client, request.app.state.http_client)
    dependencies = await checker.check_all_dependencies()
    overall_status = checker.determine_overall_status(dependencies)

    return HealthResponse(
        status=overall_status,
        service=settings.SERVICE_NAME,
        version=settings.SERVICE_VERSION,
        timestamp=datetime.now(UTC).isoformat(),
        dependencies=dependencies,
    )
