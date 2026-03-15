"""Health check service for external dependencies"""

import os

import boto3
import botocore.exceptions  # type: ignore[import-untyped]
import httpx
import redis
from app.config import Settings
from app.core.constants import ERROR_PREFIX, HTTP_OK_STATUS, HealthStatus
from common.http_client import TracedHttpClient
from common.logging import get_logger

logger = get_logger(__name__)


class HealthChecker:
    """Service for checking health of external dependencies"""

    def __init__(
        self, settings: Settings, redis_client: redis.Redis, http_client: TracedHttpClient
    ):
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

    def check_bedrock_config(self) -> str:
        """
        Check if AWS Bedrock is properly configured and credentials are valid.

        Performs a lightweight sts:GetCallerIdentity call to verify that
        the configured credentials can actually authenticate with AWS.
        Falls back to config-only checks if STS is unreachable.
        """
        if not (self.settings.BEDROCK_MODEL_ID and self.settings.BEDROCK_MODEL_ID.strip()):
            return HealthStatus.MISSING_CONFIG

        if not (self.settings.AWS_DEFAULT_REGION and self.settings.AWS_DEFAULT_REGION.strip()):
            return HealthStatus.MISSING_CONFIG

        if os.getenv("ENV") == "production" and (
            not self.settings.AWS_ACCESS_KEY_ID or not self.settings.AWS_SECRET_ACCESS_KEY
        ):
            return HealthStatus.MISSING_KEY

        return self._verify_aws_credentials()

    def _verify_aws_credentials(self) -> str:
        """Verify AWS credentials via sts:GetCallerIdentity."""
        try:
            sts = self._build_sts_client()
            sts.get_caller_identity()
            return HealthStatus.HEALTHY
        except botocore.exceptions.NoCredentialsError:
            logger.warning("aws_credentials_missing")
            return HealthStatus.MISSING_KEY
        except botocore.exceptions.ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            logger.warning("aws_credentials_invalid", error_code=error_code)
            return f"{ERROR_PREFIX}invalid credentials ({error_code})"
        except botocore.exceptions.EndpointConnectionError:
            logger.warning("aws_sts_unreachable_falling_back_to_config_check")
            return HealthStatus.CONFIGURED
        except Exception as e:
            logger.warning("aws_credential_check_failed", error=str(e))
            return f"{ERROR_PREFIX}{e}"

    def _build_sts_client(self) -> boto3.client:
        """Build a boto3 STS client using the same auth strategy as LLMService."""
        region = self.settings.AWS_DEFAULT_REGION

        if getattr(self.settings, "AWS_PROFILE", None):
            session = boto3.Session(profile_name=self.settings.AWS_PROFILE, region_name=region)
            return session.client("sts")

        kwargs: dict[str, str] = {"service_name": "sts", "region_name": region}
        if self.settings.AWS_ACCESS_KEY_ID and self.settings.AWS_SECRET_ACCESS_KEY:
            kwargs["aws_access_key_id"] = self.settings.AWS_ACCESS_KEY_ID
            kwargs["aws_secret_access_key"] = self.settings.AWS_SECRET_ACCESS_KEY

        return boto3.client(**kwargs)

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
            DependencyName.AWS_BEDROCK: self.check_bedrock_config(),
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


def verify_aws_credentials_at_startup(settings: Settings) -> None:
    """Verify AWS credentials during startup. Logs a warning if invalid.

    This is a fail-fast check: in production it raises ConfigurationError;
    in dev/local it logs a warning so the service can still start for
    non-LLM work (environment tools, testing, etc.).
    """
    from app.core.exceptions import ConfigurationError

    checker = HealthChecker(settings, redis_client=None, http_client=None)  # type: ignore[arg-type]
    status = checker._verify_aws_credentials()

    if status in {HealthStatus.HEALTHY, HealthStatus.CONFIGURED}:
        logger.info("aws_credentials_verified", status=status)
        return

    message = f"AWS credential check returned: {status}"
    if os.getenv("ENV") == "production":
        raise ConfigurationError(message)

    logger.warning("aws_credentials_not_verified", status=status, message=message)
