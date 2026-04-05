from datetime import UTC, datetime

from app.config_load import settings
from app.services.health_checker import HealthChecker
from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


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
        service=settings.app.name,
        version=settings.app.version,
        timestamp=datetime.now(UTC).isoformat(),
        dependencies=dependencies,
    )
