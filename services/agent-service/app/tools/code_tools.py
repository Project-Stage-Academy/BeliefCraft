import asyncio
import json
from typing import Any

from app.config_load import settings
from app.tools.base import BaseTool, ToolMetadata
from common.logging import get_logger
from llm_sandbox import SandboxSession  # type: ignore[import-untyped]

logger = get_logger(__name__)


class PythonSandboxTool(BaseTool):
    def __init__(self) -> None:
        super().__init__()
        self.config = settings.sandbox

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="python_sandbox",
            description=(
                "Executes a small Python snippet safely in an isolated sandbox. "
                "Returns stdout and stderr."
            ),
            category="utility",
            parameters={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "The Python code to execute. Print results to stdout.",
                    },
                    "data": {
                        "type": "object",
                        "description": (
                            "Optional JSON context. " "Injected as 'env_data' dict in the script."
                        ),
                    },
                },
                "required": ["code"],
            },
        )

    async def execute(self, **kwargs: Any) -> Any:
        return await asyncio.to_thread(self._run_in_sandbox, kwargs["code"], kwargs["data"])

    def _run_in_sandbox(self, code: str, data: dict[str, Any] | None) -> dict[str, Any]:
        script = ""
        if data:
            script += f"import json\nenv_data = json.loads('''{json.dumps(data)}''')\n\n"
        script += code

        docker_kwargs = {
            "mem_limit": self.config.memory_limit,
            "nano_cpus": int(self.config.cpus * 1e9),
            "network_disabled": self.config.network_disabled,
            "user": "1000:1000",
        }

        try:
            with SandboxSession(
                image=self.config.image, keep_template=False, **docker_kwargs
            ) as session:
                result = session.run(script)
                return {
                    "stdout": result.stdout,
                    "stderr": getattr(result, "error", ""),
                    "exit_code": getattr(result, "exit_code", 0),
                }
        except Exception as e:
            logger.error("sandbox_execution_failed", error=str(e), exc_info=True)
            return {"stdout": "", "stderr": f"Sandbox Error: {str(e)}", "exit_code": 1}
