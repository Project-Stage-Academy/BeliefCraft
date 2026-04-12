# file: tests/tools/test_code_tools.py
from unittest.mock import MagicMock, patch

import pytest
from app.tools.code_tools import PythonSandboxTool


@pytest.fixture
def mock_settings():
    """
    Mocks the global application settings for the sandbox environment.

    Why this is important: Ensures tests run deterministically without relying on
    actual environment variables and prevents
    accidental execution with unsafe limits during testing.
    """
    with patch("app.tools.code_tools.settings") as mock:
        mock.sandbox.memory_limit = "512m"
        mock.sandbox.cpus = 1.0
        mock.sandbox.network_disabled = True
        mock.sandbox.image = "python:3.11-slim"
        yield mock


@pytest.fixture
def tool(mock_settings):
    """Provides a fresh instance of the PythonSandboxTool for each test."""
    return PythonSandboxTool()


def test_get_metadata_schema_validity(tool):
    """
    Verifies the tool's metadata matches the expected JSON Schema format for LLM consumption.

    Why this is important: If the schema is invalid or missing required fields,
    the LLM agent will fail to understand how to call the tool, breaking the execution loop.
    """
    metadata = tool.get_metadata()
    assert metadata.name == "python_sandbox"
    assert metadata.category == "utility"

    props = metadata.parameters["properties"]
    assert "code" in props
    assert "data" in props
    assert props["code"]["type"] == "string"
    assert props["data"]["type"] == "object"
    assert "code" in metadata.parameters["required"]


@pytest.mark.asyncio
async def test_execute_extracts_kwargs_correctly(tool):
    """
    Tests that the async execute wrapper correctly unpacks the 'code' and 'data' kwargs.

    Why this is important: The LLM agent framework passes arguments dynamically as kwargs.
    This ensures the tool correctly bridges the generic
    interface to the specific synchronous implementation.
    """
    with patch.object(tool, "_run_in_sandbox", return_value={"exit_code": 0}) as mock_run:
        result = await tool.execute(code="print(1)", data={"a": 1})
        mock_run.assert_called_once_with("print(1)", {"a": 1})
        assert result == {"exit_code": 0}


@pytest.mark.asyncio
async def test_execute_handles_missing_optional_data(tool):
    """
    Ensures the execute method defaults the 'data' parameter to None if omitted by the LLM.

    Why this is important: The 'data' field is optional in the schema. Without a safe .get(),
    a missing key would raise a KeyError and crash the agent instead of returning a graceful error.
    """
    with patch.object(tool, "_run_in_sandbox", return_value={"exit_code": 0}) as mock_run:
        await tool.execute(code="print(1)")
        mock_run.assert_called_once_with("print(1)", None)


@pytest.mark.asyncio
async def test_execute_raises_keyerror_if_code_missing(tool):
    """
    Validates that the tool fails fast if the mandatory 'code' argument is missing.

    Why this is important: Enforces the contract that code must be provided. It is better
    to raise an exception here to immediately flag an agent generation error than to pass None.
    """
    with pytest.raises(KeyError):
        await tool.execute(data={"a": 1})


@patch("app.tools.code_tools.SandboxSession")
def test_run_in_sandbox_success_no_data(mock_session_cls, tool):
    """
    Tests a successful code execution inside the docker sandbox without environment data.

    Why this is important: Confirms the core functionality of passing a raw script to
    the session and formatting the stdout/stderr/exit_code accurately.
    """
    mock_session = MagicMock()
    mock_session_cls.return_value.__enter__.return_value = mock_session

    mock_result = MagicMock()
    mock_result.stdout = "hello\n"
    mock_result.error = ""
    mock_result.exit_code = 0
    mock_session.run.return_value = mock_result

    res = tool._run_in_sandbox("print('hello')", None)

    mock_session.run.assert_called_once_with("print('hello')")
    assert res == {"stdout": "hello\n", "stderr": "", "exit_code": 0}


@patch("app.tools.code_tools.SandboxSession")
def test_run_in_sandbox_with_complex_data_injection(mock_session_cls, tool):
    """
    Verifies that JSON data is correctly injected into the script string as 'env_data'.

    Why this is important: The use of repr(json.dumps()) prevents script termination vulnerabilities
    if the injected data contains newlines or specific quote characters.
    """
    mock_session = MagicMock()
    mock_session_cls.return_value.__enter__.return_value = mock_session
    mock_session.run.return_value = MagicMock(stdout="success", error="", exit_code=0)

    complex_data = {"key": "value with 'quotes' and \n newlines"}
    res = tool._run_in_sandbox("print(env_data['key'])", complex_data)

    injected_script = mock_session.run.call_args[0][0]
    assert "import json" in injected_script
    assert "env_data = json.loads" in injected_script
    assert "print(env_data['key'])" in injected_script
    assert res["exit_code"] == 0


@patch("app.tools.code_tools.SandboxSession")
def test_run_in_sandbox_docker_configuration(mock_session_cls, tool):
    """
    Asserts that the SandboxSession is initialized with strict security and resource limits.

    Why this is important: Prevents security regressions. If network access is accidentally enabled
    or memory limits removed, the host machine becomes vulnerable to malicious LLM-generated code.
    """
    mock_session = MagicMock()
    mock_session_cls.return_value.__enter__.return_value = mock_session
    mock_session.run.return_value = MagicMock(stdout="", error="", exit_code=0)

    tool._run_in_sandbox("pass", None)

    mock_session_cls.assert_called_once_with(
        image="python:3.11-slim",
        keep_template=False,
        mem_limit="512m",
        nano_cpus=1000000000,
        network_disabled=True,
        user="1000:1000",
    )


@patch("app.tools.code_tools.SandboxSession")
def test_run_in_sandbox_runtime_error_output(mock_session_cls, tool):
    """
    Tests that python-level errors (like SyntaxError) are correctly mapped to the stderr output.

    Why this is important: The LLM agent relies entirely on the stderr string to self-correct
    its code in the next loop. If errors are swallowed, the agent gets stuck.
    """
    mock_session = MagicMock()
    mock_session_cls.return_value.__enter__.return_value = mock_session
    mock_session.run.return_value = MagicMock(
        stdout="", error="SyntaxError: invalid syntax", exit_code=1
    )

    res = tool._run_in_sandbox("invalid python code", None)

    assert res["exit_code"] == 1
    assert res["stderr"] == "SyntaxError: invalid syntax"


@patch("app.tools.code_tools.SandboxSession")
def test_run_in_sandbox_docker_exception_handling(mock_session_cls, tool):
    """
    Ensures infrastructure-level exceptions (e.g., Docker daemon offline) are caught safely.

    Why this is important: Prevents the entire agent process from crashing due to a transient
    infrastructure issue, allowing the tool to gracefully report the failure back to the agent.
    """
    mock_session_cls.side_effect = Exception("Docker daemon not running")

    res = tool._run_in_sandbox("print(1)", None)

    assert res["stdout"] == ""
    assert res["exit_code"] == 1
    assert "Sandbox Error: Docker daemon not running" in res["stderr"]
