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
        return await asyncio.to_thread(self._run_in_sandbox, kwargs["code"], kwargs.get("data"))

    def _run_in_sandbox(self, code: str, data: dict[str, Any] | None) -> dict[str, Any]:
        """Executes the provided code within the sandbox session enforcing timeouts."""
        script = ""
        if data:
            script += f"import json\nenv_data = json.loads({repr(json.dumps(data))})\n\n"
        script += code

        docker_kwargs = {
            "mem_limit": self.config.memory_limit,
            "nano_cpus": int(self.config.cpus * 1e9),
            "network_disabled": self.config.network_disabled,
            "user": "1000:1000",
        }

        try:
            with SandboxSession(
                lang="python",
                image=self.config.image,
                keep_template=False,
                execution_timeout=self.config.timeout_seconds,
                **docker_kwargs,
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
