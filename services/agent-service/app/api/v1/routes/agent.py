from datetime import UTC, datetime
from typing import Any

import structlog
from app.models.requests import AgentQueryRequest
from app.models.responses import AgentQueryResponse
from app.services.react_agent import ReActAgent
from fastapi import APIRouter, HTTPException

logger = structlog.get_logger()
router = APIRouter()


@router.post("/agent/analyze", response_model=AgentQueryResponse)
async def analyze_query(request: AgentQueryRequest) -> AgentQueryResponse:
    """
    Analyze a warehouse query using ReAct agent (powered by Claude via AWS Bedrock).

    Example queries:
    - "Which products need reordering?"
    - "What's the risk that Order #123 will be late?"
    - "Estimate true inventory for Product X given noisy sensors"
    """
    logger.info("agent_analyze_request", query=request.query)

    start_time = datetime.now(UTC)

    try:
        agent = ReActAgent()

        final_state = await agent.run(
            user_query=request.query,
            context=request.context,
            max_iterations=request.max_iterations,
        )

        duration = (datetime.now(UTC) - start_time).total_seconds()

        reasoning_trace = []
        thoughts = final_state["thoughts"]
        tool_calls_list = final_state["tool_calls"]
        for i, thought in enumerate(thoughts):
            entry: dict[str, Any] = {
                "iteration": i + 1,
                "thought": thought.thought,
            }
            if i < len(tool_calls_list):
                tool_call = tool_calls_list[i]
                entry["action"] = {
                    "tool": tool_call.tool_name,
                    "arguments": tool_call.arguments,
                    "result": tool_call.result,
                }
            reasoning_trace.append(entry)

        response = AgentQueryResponse(
            request_id=final_state["request_id"],
            query=request.query,
            status=final_state["status"],
            answer=final_state["final_answer"],
            iterations=final_state["iteration"],
            total_tokens=final_state["total_tokens"],
            reasoning_trace=reasoning_trace,
            duration_seconds=round(duration, 2),
        )

        logger.info(
            "agent_analyze_complete",
            request_id=response.request_id,
            status=response.status,
            duration_seconds=response.duration_seconds,
        )

        return response

    except Exception as e:
        logger.error("agent_analyze_error", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Agent execution failed: {e}") from e
