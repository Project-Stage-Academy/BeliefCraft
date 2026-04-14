import json
import os
import textwrap
from typing import Any

from fastapi import FastAPI
from llm_sandbox import SandboxSession
from pydantic import BaseModel, Field

app = FastAPI()

SANDBOX_IMAGE = os.getenv("SANDBOX_IMAGE", "agent-sandbox-data-science")
SANDBOX_MEMORY_LIMIT = os.getenv("SANDBOX_MEMORY_LIMIT", "256m")
SANDBOX_CPUS = float(os.getenv("SANDBOX_CPUS", "0.5"))
SANDBOX_NETWORK_DISABLED = os.getenv("SANDBOX_NETWORK_DISABLED", "true").lower() == "true"
SANDBOX_TIMEOUT = int(os.getenv("SANDBOX_TIMEOUT_SECONDS", "10"))


class RunRequest(BaseModel):
    """Schema for incoming Python execution requests."""

    code: str = Field(min_length=1, max_length=50_000)
    data: dict[str, Any] = Field(default_factory=dict)


class RunResponse(BaseModel):
    """Schema for sandbox execution results."""

    stdout: str
    stderr: str
    exit_code: int


@app.get("/health")
def health_check() -> dict[str, str]:
    """Verify the service is running and ready to accept requests."""
    return {"status": "ok", "service": "sandbox-runner"}


def _build_script(code: str, data: dict[str, Any]) -> str:
    """Construct the executable script with a foolproof error catcher."""

    env_json = repr(json.dumps(data))
    indented_code = textwrap.indent(code, "    ")

    return f"""import json
import sys
import traceback

env_data = json.loads({env_json})

try:
{indented_code}
except Exception as e:
    # Force the traceback into stdout so the agent ALWAYS sees it
    print("\\n" + "="*40)
    print("PYTHON EXECUTION ERROR:")
    print("="*40)
    traceback.print_exc(file=sys.stdout)
    sys.exit(1)
"""


@app.post("/run", response_model=RunResponse)
def run_python(request: RunRequest) -> RunResponse:
    """Execute the provided Python script inside an isolated Docker container."""
    script = _build_script(request.code, request.data)

    with SandboxSession(
        lang="python",
        image=SANDBOX_IMAGE,
        keep_template=False,
        execution_timeout=SANDBOX_TIMEOUT,
        mem_limit=SANDBOX_MEMORY_LIMIT,
        nano_cpus=int(SANDBOX_CPUS * 1e9),
        network_disabled=SANDBOX_NETWORK_DISABLED,
        user="1000:1000",
    ) as session:
        result = session.run(script)
        return RunResponse(
            stdout=result.stdout,
            stderr=getattr(result, "error", ""),
            exit_code=getattr(result, "exit_code", 0),
        )
