from typing import Any

from app.config_load import settings
from app.tools.base import BaseTool, ToolMetadata
from common.http_client import TracedHttpClient
from common.logging import get_logger

logger = get_logger(__name__)


class PythonSandboxTool(BaseTool):
    def __init__(self) -> None:
        super().__init__()
        self.config = settings.sandbox

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="python_sandbox",
            description=(
                "Executes Python snippets in an isolated sandbox. "
                "Workflow: 1) Retrieve necessary code from RAG. "
                "2) Retrieve context from the environment. "
                "3) Combine them into a single script. "
                "4) Pass the script to this tool. "
                "5) Evaluate 'stdout', 'stderr', and 'exit_code' "
                "to determine if the execution succeeded."
            ),
            category="utility",
            parameters={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": (
                            "The executable Python script. Must be raw, "
                            "valid Python code without markdown "
                            "formatting (do not wrap in ```python). "
                            "Access environment variables via the "
                            "'env_data' dictionary. You MUST print the final "
                            "result to stdout, as only "
                            "stdout and stderr are returned."
                        ),
                    },
                    "data": {
                        "type": "object",
                        "description": (
                            "Environment data to be processed. "
                            "Passed as a JSON object and injected "
                            "automatically as a dictionary named 'env_data' "
                            "inside the script. "
                            "Do not hardcode environment variables into the "
                            "'code' string; use this parameter."
                        ),
                    },
                },
                "required": ["code"],
            },
        )

    async def execute(self, **kwargs: Any) -> Any:
        payload = {
            "code": kwargs["code"],
            "data": kwargs.get("data", {}),
        }

        async with TracedHttpClient(
            settings.sandbox.runner_url,
            timeout=settings.sandbox.timeout_seconds,
        ) as client:
            response = await client.post("/run", json=payload)
            response.raise_for_status()
            return response.json()
