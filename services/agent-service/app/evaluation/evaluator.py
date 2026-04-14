"""Agent evaluation framework implementation."""

import ast
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from app.clients.rag_mcp_client import RAGMCPClient
from app.config_load import settings
from app.evaluation.models import (
    CategoryStats,
    EvaluationReport,
    EvaluationResult,
    EvaluationScenario,
)
from app.models.responses import AgentRecommendationResponse, Citation
from app.prompts.system_prompts import get_warehouse_advisor_prompt
from app.services.react_agent import ReActAgent
from app.services.recommendation_generator import RecommendationGenerator
from app.tools.registration import get_skill_store, register_mcp_rag_tools
from common.logging import get_logger

logger = get_logger(__name__)

_mcp_rag_tools = []
_rag_tools_registered = False


# Maps the top-level title segment (lowercase) to book section number.
# Derived from entity_number prefixes present in RAG knowledge base chunks.
_TITLE_SECTION_MAP: dict[str, str] = {
    "introduction": "1",
    "probabilistic reasoning": "2",
    "sequential problems": "11",
    "model uncertainty": "15",
    "state uncertainty": "19",
}


class AgentEvaluator:
    """
    Agent evaluation framework.

    Loads test scenarios from YAML, runs agent for each scenario,
    computes evaluation metrics, and generates aggregated reports.
    """

    def __init__(self, scenarios_path: str | Path | None = None) -> None:
        """
        Initialize evaluator.

        Args:
            scenarios_path: Path to YAML file with test scenarios.
                           Defaults to app/evaluation/test_scenarios.yaml
        """
        if scenarios_path is None:
            scenarios_path = Path(__file__).parent / "test_scenarios.yaml"
        else:
            scenarios_path = Path(scenarios_path)

        self.scenarios_path = scenarios_path
        self.scenarios = self._load_scenarios()

        logger.info(
            "evaluator_initialized",
            scenarios_count=len(self.scenarios),
            scenarios_path=str(scenarios_path),
        )

    def _load_scenarios(self) -> list[EvaluationScenario]:
        """Load and validate scenarios from YAML."""
        if not self.scenarios_path.exists():
            logger.error("scenarios_file_not_found", path=str(self.scenarios_path))
            raise FileNotFoundError(f"Scenarios file not found: {self.scenarios_path}")

        with self.scenarios_path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)

        raw_scenarios = data.get("scenarios", [])
        scenarios = [EvaluationScenario.model_validate(s) for s in raw_scenarios]

        logger.info("scenarios_loaded", count=len(scenarios))
        return scenarios

    async def run_evaluation(
        self,
        scenario_ids: list[str] | None = None,
    ) -> EvaluationReport:
        """
        Run evaluation on specified scenarios.

        Args:
            scenario_ids: List of scenario IDs to run. If None, runs all.

        Returns:
            EvaluationReport with aggregated results.
        """
        await self._ensure_rag_tools_registered()

        if scenario_ids:
            scenarios_to_run = [s for s in self.scenarios if s.id in scenario_ids]
            if not scenarios_to_run:
                raise ValueError(f"No scenarios found with IDs: {scenario_ids}")
        else:
            scenarios_to_run = self.scenarios

        logger.info("evaluation_started", scenarios_count=len(scenarios_to_run))

        results: list[EvaluationResult] = []

        for scenario in scenarios_to_run:
            logger.info("evaluating_scenario", scenario_id=scenario.id)
            try:
                result = await self._evaluate_scenario(scenario)
                results.append(result)
                logger.info(
                    "scenario_evaluated",
                    scenario_id=scenario.id,
                    passed=result.passed,
                    score=result.overall_score,
                )
            except Exception as e:
                logger.error(
                    "scenario_evaluation_failed",
                    scenario_id=scenario.id,
                    error=str(e),
                    exc_info=True,
                )
                results.append(self._create_failed_result(scenario, str(e)))

        report = self._generate_report(results)
        logger.info(
            "evaluation_completed",
            report_id=report.report_id,
            pass_rate=report.pass_rate,
        )

        return report

    async def _ensure_rag_tools_registered(self) -> None:
        """Register RAG tools from MCP server if not already done."""
        global _rag_tools_registered, _mcp_rag_tools
        if _rag_tools_registered:
            return

        from app.tools.factory import ToolRegistryFactory

        mcp_client = RAGMCPClient(base_url=settings.external_services.rag_api_url)
        try:
            await mcp_client.connect()

            # 1. Create a temporary registry
            temp_registry = ToolRegistryFactory.create_react_agent_registry()

            # 2. Pass the registry to the registration function
            await register_mcp_rag_tools(mcp_client, registry=temp_registry)

            # 3. Extract and store the tools for agent instantiation later
            _mcp_rag_tools = [
                t for t in temp_registry.tools.values() if t.get_metadata().category == "rag"
            ]

            _rag_tools_registered = True
            logger.info(
                "evaluator_rag_tools_registered", rag_url=settings.external_services.rag_api_url
            )
        except Exception as e:
            logger.warning(
                "evaluator_rag_tools_registration_failed",
                error=str(e),
                message="Evaluation will continue without RAG tools; citation metrics may fail",
            )

    async def _evaluate_scenario(
        self,
        scenario: EvaluationScenario,
    ) -> EvaluationResult:
        """
        Evaluate a single scenario.

        Args:
            scenario: Test scenario to evaluate.

        Returns:
            EvaluationResult with computed metrics.
        """
        skill_store = get_skill_store()
        if skill_store:
            skill_catalog = skill_store.get_skill_catalog()
            system_prompt = get_warehouse_advisor_prompt(skill_catalog=skill_catalog)
        else:
            system_prompt = get_warehouse_advisor_prompt()

        agent = ReActAgent(system_prompt=system_prompt)

        started_at = datetime.now(UTC)

        final_state = await agent.run(
            user_query=scenario.query,
            context=scenario.context,
            max_iterations=scenario.max_iterations,
        )

        execution_time = (datetime.now(UTC) - started_at).total_seconds()

        generator = RecommendationGenerator()
        response = await generator.generate(final_state)

        metrics = self._compute_metrics(scenario, response)

        return EvaluationResult(
            scenario_id=scenario.id,
            scenario_category=scenario.category,
            query=scenario.query,
            difficulty=scenario.difficulty,
            agent_status=response.status,
            iterations=response.iterations,
            execution_time_seconds=execution_time,
            retrieval_accuracy=metrics["retrieval_accuracy"],
            citation_quality=metrics["citation_quality"],
            code_validity=metrics["code_validity"],
            reasoning_quality=metrics["reasoning_quality"],
            actionability=metrics["actionability"],
            overall_score=metrics["overall_score"],
            passed=metrics["passed"],
            failure_reasons=metrics["failure_reasons"],
            algorithm_found=response.algorithm,
            citations_count=len(response.citations),
            code_snippets_count=len(response.code_snippets),
            recommendations_count=len(response.recommendations),
            tools_used=response.tools_used,
            full_response=response.model_dump(),
        )

    def _compute_metrics(
        self,
        scenario: EvaluationScenario,
        response: AgentRecommendationResponse,
    ) -> dict[str, Any]:
        """
        Compute evaluation metrics for a scenario/response pair.

        Args:
            scenario: Test scenario with expected output criteria.
            response: Agent response to evaluate.

        Returns:
            Dictionary with metric scores and pass/fail status.
        """
        expected = scenario.expected_output
        failure_reasons: list[str] = []

        retrieval_accuracy = self._compute_retrieval_accuracy(
            expected.must_include,
            response,
            failure_reasons,
        )
        citation_quality = self._compute_citation_quality(
            expected.must_cite,
            response,
            failure_reasons,
        )
        code_validity = self._compute_code_validity(response, failure_reasons)
        reasoning_quality = self._compute_reasoning_quality(response, failure_reasons)
        actionability = self._compute_actionability(
            expected.must_include,
            response,
            failure_reasons,
        )

        overall_score = (
            retrieval_accuracy * 0.3
            + citation_quality * 0.2
            + code_validity * 0.15
            + reasoning_quality * 0.15
            + actionability * 0.2
        )

        passed = (
            overall_score >= 0.7 and response.status == "completed" and len(failure_reasons) == 0
        )

        return {
            "retrieval_accuracy": retrieval_accuracy,
            "citation_quality": citation_quality,
            "code_validity": code_validity,
            "reasoning_quality": reasoning_quality,
            "actionability": actionability,
            "overall_score": overall_score,
            "passed": passed,
            "failure_reasons": failure_reasons,
        }

    def _compute_retrieval_accuracy(
        self,
        must_include: dict[str, Any],
        response: AgentRecommendationResponse,
        failure_reasons: list[str],
    ) -> float:
        """
        Compute retrieval accuracy (0-1).

        Checks if agent found expected algorithm/formula/code elements.
        """
        score = 1.0

        if "algorithm" in must_include:
            expected_pattern = must_include["algorithm"]
            if isinstance(expected_pattern, str) and (
                not response.algorithm
                or not re.search(
                    expected_pattern,
                    response.algorithm,
                    re.IGNORECASE,
                )
            ):
                score -= 0.5
                failure_reasons.append(
                    f"Expected algorithm pattern: {expected_pattern}, got: {response.algorithm}"
                )

        if must_include.get("formula") is True and len(response.formulas) == 0:
            score -= 0.3
            failure_reasons.append("Expected formulas, but none found")

        if must_include.get("code") is True and len(response.code_snippets) == 0:
            score -= 0.2
            failure_reasons.append("Expected code snippets, but none found")

        return max(0.0, score)

    def _compute_citation_quality(
        self,
        must_cite: dict[str, Any],
        response: AgentRecommendationResponse,
        failure_reasons: list[str],
    ) -> float:
        """
        Compute citation quality (0-1).

        Checks if citations meet expected criteria (chapters, entity types, etc.).
        """
        if not must_cite:
            return 1.0

        if len(response.citations) == 0:
            failure_reasons.append("No citations provided")
            return 0.0

        score = 1.0

        if "section" in must_cite:
            expected_sections = must_cite["section"]
            if isinstance(expected_sections, list):
                found_sections = {
                    self._extract_section_from_citation(c) for c in response.citations
                } - {None}
                has_expected_section = bool(found_sections & set(expected_sections))
                if not has_expected_section:
                    score -= 0.5
                    failure_reasons.append(f"Expected citations from sections {expected_sections}")

        return max(0.0, score)

    def _compute_code_validity(
        self,
        response: AgentRecommendationResponse,
        failure_reasons: list[str],
    ) -> float:
        """
        Compute code validity (0-1).

        Validates Python code snippets using AST parsing.
        """
        if len(response.code_snippets) == 0:
            return 1.0

        valid_count = 0
        total_count = len(response.code_snippets)

        for snippet in response.code_snippets:
            if snippet.language.lower() == "python":
                try:
                    ast.parse(snippet.code)
                    valid_count += 1
                except SyntaxError as e:
                    failure_reasons.append(f"Invalid Python code: {e}")
            else:
                valid_count += 1

        return valid_count / total_count if total_count > 0 else 1.0

    def _compute_reasoning_quality(
        self,
        response: AgentRecommendationResponse,
        failure_reasons: list[str],
    ) -> float:
        """
        Compute reasoning quality (0-1).

        Checks if reasoning trace is logical and complete.
        """
        score = 1.0

        if len(response.reasoning_trace) == 0:
            score -= 0.5
            failure_reasons.append("No reasoning trace provided")

        if response.analysis and len(response.analysis) < 50:
            score -= 0.3
            failure_reasons.append("Analysis too short")

        return max(0.0, score)

    def _compute_actionability(
        self,
        must_include: dict[str, Any],
        response: AgentRecommendationResponse,
        failure_reasons: list[str],
    ) -> float:
        """
        Compute actionability (0-1).

        Checks if recommendations are specific and implementable.
        """
        score = 1.0

        if len(response.recommendations) == 0:
            score = 0.0
            failure_reasons.append("No recommendations provided")
            return score

        if "recommendations" in must_include:
            criteria = must_include["recommendations"]
            if isinstance(criteria, dict):
                min_count = criteria.get("min_count", 1)
                max_count = criteria.get("max_count")

                if len(response.recommendations) < min_count:
                    score -= 0.5
                    failure_reasons.append(
                        f"Expected at least {min_count} recommendations, "
                        f"got {len(response.recommendations)}"
                    )

                if max_count and len(response.recommendations) > max_count:
                    score -= 0.3
                    failure_reasons.append(
                        f"Expected at most {max_count} recommendations, "
                        f"got {len(response.recommendations)}"
                    )

        for rec in response.recommendations:
            if len(rec.action) < 10:
                score -= 0.2
                failure_reasons.append("Recommendation action too vague")
                break

        return max(0.0, score)

    @staticmethod
    def _extract_section_from_citation(citation: Citation) -> str | None:
        """Extract book section number from a citation.

        Strategy:
        1. Parse the integer prefix from entity_number (e.g. "11.4" → "11").
        2. Fall back to the top-level title segment mapped via _TITLE_SECTION_MAP.
        """

        if citation.entity_number:
            prefix = citation.entity_number.split(".")[0]
            if prefix.isdigit():
                return prefix
        if citation.title:
            first_segment = citation.title.lower().split(" / ")[0].strip()
            return _TITLE_SECTION_MAP.get(first_segment) or None
        return None

    def _create_failed_result(
        self,
        scenario: EvaluationScenario,
        error: str,
    ) -> EvaluationResult:
        """Create a failed evaluation result for exception cases."""
        return EvaluationResult(
            scenario_id=scenario.id,
            scenario_category=scenario.category,
            query=scenario.query,
            difficulty=scenario.difficulty,
            agent_status="failed",
            iterations=0,
            execution_time_seconds=0.0,
            retrieval_accuracy=0.0,
            citation_quality=0.0,
            code_validity=0.0,
            reasoning_quality=0.0,
            actionability=0.0,
            overall_score=0.0,
            passed=False,
            failure_reasons=[f"Evaluation failed: {error}"],
        )

    def _generate_report(self, results: list[EvaluationResult]) -> EvaluationReport:
        """Generate aggregated evaluation report from individual results."""
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        failed = total - passed
        pass_rate = passed / total if total > 0 else 0.0

        avg_retrieval = sum(r.retrieval_accuracy for r in results) / total if total > 0 else 0.0
        avg_citation = sum(r.citation_quality for r in results) / total if total > 0 else 0.0
        avg_code = sum(r.code_validity for r in results) / total if total > 0 else 0.0
        avg_reasoning = sum(r.reasoning_quality for r in results) / total if total > 0 else 0.0
        avg_actionability = sum(r.actionability for r in results) / total if total > 0 else 0.0
        avg_overall = sum(r.overall_score for r in results) / total if total > 0 else 0.0

        avg_execution = sum(r.execution_time_seconds for r in results) / total if total > 0 else 0.0
        avg_iterations = sum(r.iterations for r in results) / total if total > 0 else 0.0

        by_category: dict[str, list[EvaluationResult]] = {}
        for result in results:
            by_category.setdefault(result.scenario_category, []).append(result)

        by_difficulty: dict[str, list[EvaluationResult]] = {}
        for result in results:
            by_difficulty.setdefault(result.difficulty, []).append(result)

        category_stats = {
            cat: self._compute_category_stats(cat_results)
            for cat, cat_results in by_category.items()
        }

        difficulty_stats = {
            diff: self._compute_category_stats(diff_results)
            for diff, diff_results in by_difficulty.items()
        }

        failed_scenarios = [r.scenario_id for r in results if not r.passed]

        return EvaluationReport(
            report_id=str(uuid4()),
            total_scenarios=total,
            passed=passed,
            failed=failed,
            pass_rate=pass_rate,
            avg_retrieval_accuracy=avg_retrieval,
            avg_citation_quality=avg_citation,
            avg_code_validity=avg_code,
            avg_reasoning_quality=avg_reasoning,
            avg_actionability=avg_actionability,
            avg_overall_score=avg_overall,
            avg_execution_time=avg_execution,
            avg_iterations=avg_iterations,
            results_by_category=category_stats,
            results_by_difficulty=difficulty_stats,
            failed_scenarios=failed_scenarios,
            results=results,
        )

    def _compute_category_stats(
        self,
        results: list[EvaluationResult],
    ) -> CategoryStats:
        """Compute statistics for a group of results."""
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        pass_rate = passed / total if total > 0 else 0.0
        avg_score = sum(r.overall_score for r in results) / total if total > 0 else 0.0

        return CategoryStats(
            total=total,
            passed=passed,
            pass_rate=pass_rate,
            avg_score=avg_score,
        )
