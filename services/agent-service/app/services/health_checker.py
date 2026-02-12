"""Health check service for external dependencies"""

import httpx
import redis
from app.config import Settings
from app.core.constants import ERROR_PREFIX, HTTP_OK_STATUS, HealthStatus


class HealthChecker:
    """Service for checking health of external dependencies"""

    def __init__(
        self,
        settings: Settings,
        redis_client: redis.Redis,
        http_client: httpx.AsyncClient,
    ) -> None:
        self.settings = settings
        self._redis_client = redis_client
        self._http_client = http_client

    async def check_http_endpoint(self, url: str) -> str:
        """
        Check health of an HTTP endpoint
        Args:
            url: The endpoint URL to check

        Returns:
            Health status string
        """
        try:
            response = await self._http_client.get(f"{url}/health")
            return (
                HealthStatus.HEALTHY
                if response.status_code == HTTP_OK_STATUS
                else HealthStatus.UNHEALTHY
            )
        except httpx.TimeoutException:
            return f"{ERROR_PREFIX}timeout"
        except httpx.ConnectError:
            return f"{ERROR_PREFIX}connection refused"
        except Exception as e:
            return f"{ERROR_PREFIX}{str(e)}"

    def check_redis(self) -> str:
        """
        Check Redis connectivity
        Returns:
            Health status string
        """
        try:
            self._redis_client.ping()
            return HealthStatus.HEALTHY
        except redis.ConnectionError:
            return f"{ERROR_PREFIX}connection refused"
        except redis.TimeoutError:
            return f"{ERROR_PREFIX}timeout"
        except Exception as e:
            return f"{ERROR_PREFIX}{str(e)}"

    def check_anthropic_config(self) -> str:
        """
        Check if Anthropic API key is configured
        Returns:
            Configuration status string
        """
        return (
            HealthStatus.CONFIGURED
            if (self.settings.ANTHROPIC_API_KEY and self.settings.ANTHROPIC_API_KEY.strip())
            else HealthStatus.MISSING_KEY
        )

    async def check_all_dependencies(self) -> dict[str, str]:
        """
        Check all external dependencies
        Returns:
            Dictionary with dependency names and their statuses
        """
        from app.core.constants import DependencyName

        return {
            DependencyName.ENVIRONMENT_API: await self.check_http_endpoint(
                self.settings.ENVIRONMENT_API_URL
            ),
            DependencyName.RAG_API: await self.check_http_endpoint(self.settings.RAG_API_URL),
            DependencyName.REDIS: self.check_redis(),
            DependencyName.ANTHROPIC: self.check_anthropic_config(),
        }

    @staticmethod
    def determine_overall_status(dependencies: dict[str, str]) -> str:
        """
        Determine overall health status based on all dependencies
        Args:
            dependencies: Dictionary of dependency statuses

        Returns:
            Overall health status
        """
        healthy_statuses = {HealthStatus.HEALTHY, HealthStatus.CONFIGURED}
        all_healthy = all(status in healthy_statuses for status in dependencies.values())
        return HealthStatus.HEALTHY if all_healthy else HealthStatus.DEGRADED
