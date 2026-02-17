from datetime import UTC, datetime

from app.models.requests import AgentQueryRequest
from app.models.responses import AgentQueryResponse
from app.services.react_agent import ReActAgent
from app.services.reasoning_trace_formatter import ReasoningTraceFormatter
from common.logging import get_logger
from fastapi import APIRouter, HTTPException

logger = get_logger(__name__)
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

        formatter = ReasoningTraceFormatter()
        reasoning_trace = formatter.format(final_state)

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
