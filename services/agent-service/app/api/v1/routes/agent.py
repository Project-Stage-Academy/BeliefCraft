from app.models.requests import AgentQueryRequest
from app.models.responses import AgentRecommendationResponse
from app.services.react_agent import ReActAgent
from app.services.recommendation_generator import RecommendationGenerator
from app.models.responses import AgentQueryResponse
from app.prompts.system_prompts import get_warehouse_advisor_prompt
from app.services.react_agent import ReActAgent
from app.services.reasoning_trace_formatter import ReasoningTraceFormatter
from app.tools import get_skill_store
from common.logging import get_logger
from fastapi import APIRouter, HTTPException

logger = get_logger(__name__)
router = APIRouter()


@router.post("/agent/analyze", response_model=AgentRecommendationResponse)
async def analyze_query(request: AgentQueryRequest) -> AgentRecommendationResponse:
    """
    Analyze a warehouse query using ReAct agent (powered by Claude via AWS Bedrock).

    Example queries:
    - "Which products need reordering?"
    - "What's the risk that Order #123 will be late?"
    - "Estimate true inventory for Product X given noisy sensors"
    """
    logger.info("agent_analyze_request", query=request.query)

    try:
        # Generate system prompt with skill catalog if available
        skill_store = get_skill_store()
        if skill_store:
            skill_catalog = skill_store.get_skill_catalog()
            system_prompt = get_warehouse_advisor_prompt(skill_catalog=skill_catalog)
            logger.debug(
                "agent_initialized_with_skills",
                skills_count=len(skill_store.get_skill_names()),
            )
        else:
            system_prompt = get_warehouse_advisor_prompt()
            logger.debug("agent_initialized_without_skills")

        agent = ReActAgent(system_prompt=system_prompt)

        final_state = await agent.run(
            user_query=request.query,
            context=request.context,
            max_iterations=request.max_iterations,
        )

        generator = RecommendationGenerator()
        response = await generator.generate(final_state)

        logger.info(
            "agent_analyze_complete",
            request_id=response.request_id,
            status=response.status,
            execution_time_seconds=response.execution_time_seconds,
        )

        return response

    except Exception as e:
        logger.error("agent_analyze_error", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Agent execution failed: {e}") from e
