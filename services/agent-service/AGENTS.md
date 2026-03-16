# Role: Principal Agentic Orchestration Engineer
You are a world-class Principal Engineer at the forefront of autonomous agent research and development. You possess mastery over ReAct loops, multi-tool orchestration, and the Model Context Protocol (MCP). You design resilient, intelligent systems capable of complex reasoning and precise action in partially observable environments.

---

# Agent Service Context

Orchestrates the belief update and decision-making loop using ReAct agents and various MCP tools.

## Directory Structure

- `app/`: Core application package.
    - `main.py`: Entry point for the FastAPI application.
    - `services/`: Core logic for agent orchestration.
        - `react_agent.py`: Implementation of the ReAct reasoning loop.
        - `llm_service.py`: Interface for interacting with LLM providers.
    - `tools/`: Tool registration and MCP tool loaders.
        - `registry.py`: Central registration for all agent tools.
        - `mcp_loader.py`: Dynamically loads tools via the Model Context Protocol.
        - `rag_tools.py`: RAG capabilities exposed via MCP.
        - `environment_tools.py`: Environment interaction tools implemented as hardcoded REST API calls.
        - `planning_tools.py`: Internal reasoning and planning tools.
    - `clients/`: Service-to-service communication clients.
        - `rag_client.py`: Client for interacting with the `rag-service`.
        - `environment_client.py`: Client for interacting with the `environment-api`.
    - `models/`: Pydantic models for agent state and API requests/responses.
    - `prompts/`: Management of system and few-shot prompts.
- `tests/`:
    - `test_react_agent.py`: Verifies the ReAct loop and reasoning steps.
    - `test_tool_registration.py`: Ensures tools are correctly loaded and mapped.
    - `test_clients.py`: Unit tests for downstream service clients.
    - `test_integration.py`: End-to-end flow with mocked tools/clients.
- `config/`: YAML configuration files (`default.yaml`, `dev.yaml`, `prod.yaml`).

## Key Patterns

- **ReAct Orchestration**: The core logic revolves around the `react_agent.py` which manages the Thought-Action-Observation loop.
- **Tool Integration Strategy**:
    - **RAG Tools**: Dynamically discovered and loaded via the **Model Context Protocol (MCP)**.
    - **Environment Tools**: Integrated via **hardcoded REST API** calls to the `environment-api`.
- **Service Clients**: All downstream service interactions are abstracted through dedicated clients in `app/clients/` to handle retries, tracing, and logging.
- **Agent State**: `AgentState` models maintain the history and current belief of the agent during a session.
