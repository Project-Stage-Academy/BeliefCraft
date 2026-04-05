"""Tests for agent evaluator."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.evaluation.evaluator import AgentEvaluator
from app.models.responses import AgentRecommendationResponse, Recommendation


@pytest.fixture
def minimal_scenarios_yaml() -> str:
    """Minimal valid scenarios YAML for testing."""
    return """
scenarios:
  - id: "test_scenario_001"
    category: "test_category"
    query: "Test query for evaluation"
    max_iterations: 3
    expected_output:
      must_include:
        algorithm: "test algorithm"
        formula: true
      must_cite:
        chapter: [3, 4]
    evaluation_criteria:
      retrieval_accuracy: "Should find test algorithm"
    difficulty: "easy"
"""


@pytest.fixture
def temp_scenarios_file(minimal_scenarios_yaml: str) -> Path:
    """Create temporary scenarios file."""
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".yaml",
        delete=False,
        encoding="utf-8",
    ) as f:
        f.write(minimal_scenarios_yaml)
        return Path(f.name)


class TestAgentEvaluator:
    """Tests for AgentEvaluator class."""

    def test_init_with_custom_path(self, temp_scenarios_file: Path) -> None:
        evaluator = AgentEvaluator(scenarios_path=temp_scenarios_file)

        assert evaluator.scenarios_path == temp_scenarios_file
        assert len(evaluator.scenarios) == 1

        temp_scenarios_file.unlink()

    def test_init_raises_on_missing_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            AgentEvaluator(scenarios_path="/nonexistent/path.yaml")

    def test_load_scenarios(self, temp_scenarios_file: Path) -> None:
        evaluator = AgentEvaluator(scenarios_path=temp_scenarios_file)

        assert len(evaluator.scenarios) == 1
        scenario = evaluator.scenarios[0]
        assert scenario.id == "test_scenario_001"
        assert scenario.category == "test_category"
        assert scenario.max_iterations == 3

        temp_scenarios_file.unlink()

    @pytest.mark.asyncio
    async def test_run_evaluation_success(self, temp_scenarios_file: Path) -> None:
        evaluator = AgentEvaluator(scenarios_path=temp_scenarios_file)

        mock_response = AgentRecommendationResponse(
            request_id="test_req",
            query="Test query",
            task="Test task",
            analysis="Test analysis",
            algorithm="test algorithm",
            recommendations=[
                Recommendation(
                    action="Test action",
                    priority="high",
                    rationale="Test rationale",
                )
            ],
            status="completed",
            iterations=2,
            total_tokens=100,
            execution_time_seconds=1.5,
        )

        with (
            patch("app.evaluation.evaluator.ReActAgent") as mock_agent_cls,
            patch("app.evaluation.evaluator.RecommendationGenerator") as mock_gen_cls,
            patch("app.evaluation.evaluator.get_skill_store", return_value=None),
        ):
            mock_agent = MagicMock()
            mock_agent.run = AsyncMock(return_value={"status": "completed"})
            mock_agent_cls.return_value = mock_agent

            mock_generator = MagicMock()
            mock_generator.generate = AsyncMock(return_value=mock_response)
            mock_gen_cls.return_value = mock_generator

            report = await evaluator.run_evaluation()

            assert report.total_scenarios == 1
            assert report.passed >= 0
            assert report.pass_rate >= 0.0
            assert len(report.results) == 1

        temp_scenarios_file.unlink()

    @pytest.mark.asyncio
    async def test_run_evaluation_with_scenario_filter(
        self,
        temp_scenarios_file: Path,
    ) -> None:
        evaluator = AgentEvaluator(scenarios_path=temp_scenarios_file)

        mock_response = AgentRecommendationResponse(
            request_id="test_req",
            query="Test query",
            task="Test task",
            analysis="Test analysis",
            recommendations=[
                Recommendation(
                    action="Test action",
                    priority="high",
                    rationale="Test rationale",
                )
            ],
            status="completed",
            iterations=2,
            total_tokens=100,
            execution_time_seconds=1.5,
        )

        with (
            patch("app.evaluation.evaluator.ReActAgent") as mock_agent_cls,
            patch("app.evaluation.evaluator.RecommendationGenerator") as mock_gen_cls,
            patch("app.evaluation.evaluator.get_skill_store", return_value=None),
        ):
            mock_agent = MagicMock()
            mock_agent.run = AsyncMock(return_value={"status": "completed"})
            mock_agent_cls.return_value = mock_agent

            mock_generator = MagicMock()
            mock_generator.generate = AsyncMock(return_value=mock_response)
            mock_gen_cls.return_value = mock_generator

            report = await evaluator.run_evaluation(scenario_ids=["test_scenario_001"])

            assert report.total_scenarios == 1

        temp_scenarios_file.unlink()

    @pytest.mark.asyncio
    async def test_run_evaluation_invalid_scenario_id(
        self,
        temp_scenarios_file: Path,
    ) -> None:
        evaluator = AgentEvaluator(scenarios_path=temp_scenarios_file)

        with pytest.raises(ValueError, match="No scenarios found"):
            await evaluator.run_evaluation(scenario_ids=["nonexistent"])

        temp_scenarios_file.unlink()

    def test_compute_retrieval_accuracy(self, temp_scenarios_file: Path) -> None:
        evaluator = AgentEvaluator(scenarios_path=temp_scenarios_file)

        must_include = {"algorithm": "reorder point"}
        response = AgentRecommendationResponse(
            request_id="test",
            query="Test",
            task="Test",
            analysis="Test",
            algorithm="reorder point algorithm",
            recommendations=[
                Recommendation(
                    action="Test",
                    priority="high",
                    rationale="Test",
                )
            ],
            status="completed",
            iterations=1,
            total_tokens=50,
            execution_time_seconds=1.0,
        )
        failure_reasons: list[str] = []

        score = evaluator._compute_retrieval_accuracy(
            must_include,
            response,
            failure_reasons,
        )

        assert score > 0.0
        assert len(failure_reasons) == 0

        temp_scenarios_file.unlink()

    def test_compute_code_validity(self, temp_scenarios_file: Path) -> None:
        evaluator = AgentEvaluator(scenarios_path=temp_scenarios_file)

        from app.models.responses import CodeSnippet

        response = AgentRecommendationResponse(
            request_id="test",
            query="Test",
            task="Test",
            analysis="Test",
            code_snippets=[
                CodeSnippet(
                    language="python",
                    code="x = 1 + 2\nprint(x)",
                    validated=True,
                )
            ],
            recommendations=[
                Recommendation(
                    action="Test",
                    priority="high",
                    rationale="Test",
                )
            ],
            status="completed",
            iterations=1,
            total_tokens=50,
            execution_time_seconds=1.0,
        )
        failure_reasons: list[str] = []

        score = evaluator._compute_code_validity(response, failure_reasons)

        assert score == 1.0

        temp_scenarios_file.unlink()

    def test_compute_code_validity_invalid_code(
        self,
        temp_scenarios_file: Path,
    ) -> None:
        evaluator = AgentEvaluator(scenarios_path=temp_scenarios_file)

        from app.models.responses import CodeSnippet

        response = AgentRecommendationResponse(
            request_id="test",
            query="Test",
            task="Test",
            analysis="Test",
            code_snippets=[
                CodeSnippet(
                    language="python",
                    code="def invalid syntax here",
                )
            ],
            recommendations=[
                Recommendation(
                    action="Test",
                    priority="high",
                    rationale="Test",
                )
            ],
            status="completed",
            iterations=1,
            total_tokens=50,
            execution_time_seconds=1.0,
        )
        failure_reasons: list[str] = []

        score = evaluator._compute_code_validity(response, failure_reasons)

        assert score == 0.0
        assert len(failure_reasons) > 0

        temp_scenarios_file.unlink()
