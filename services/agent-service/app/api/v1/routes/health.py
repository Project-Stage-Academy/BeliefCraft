from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.config import Settings, get_settings
from app.services.health_checker import HealthChecker
from datetime import datetime, timezone

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response model"""
    status: str
    service: str
    version: str
    timestamp: str
    dependencies: dict[str, str]


@router.get("/health", response_model=HealthResponse)
async def health_check(settings: Settings = Depends(get_settings)) -> HealthResponse:
    """
    Health check endpoint - verifies service and dependencies
    
    Returns:
        HealthResponse with overall status and individual dependency statuses
    """
    checker = HealthChecker(settings)
    dependencies = await checker.check_all_dependencies()
    overall_status = checker.determine_overall_status(dependencies)
    
    return HealthResponse(
        status=overall_status,
        service=settings.SERVICE_NAME,
        version=settings.SERVICE_VERSION,
        timestamp=datetime.now(timezone.utc).isoformat(),
        dependencies=dependencies
    )
