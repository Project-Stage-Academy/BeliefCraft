"""Tests for evaluation models."""

from datetime import datetime

import pytest
from app.evaluation.models import (
    CategoryStats,
    EvaluationReport,
    EvaluationResult,
    EvaluationScenario,
    ExpectedOutput,
)


class TestEvaluationScenario:
    """Tests for EvaluationScenario model."""

    def test_valid_scenario(self) -> None:
        scenario = EvaluationScenario(
            id="test_001",
            category="inventory",
            query="Test query for inventory",
            max_iterations=3,
            expected_output=ExpectedOutput(
                must_include={"algorithm": "reorder point"},
                must_cite={"chapter": [3, 4]},
            ),
            difficulty="easy",
        )

        assert scenario.id == "test_001"
        assert scenario.category == "inventory"
        assert scenario.max_iterations == 3
        assert scenario.difficulty == "easy"

    def test_scenario_with_context(self) -> None:
        scenario = EvaluationScenario(
            id="test_002",
            category="supplier",
            query="Query with context",
            context={"warehouse_id": "wh-001"},
            max_iterations=5,
            expected_output=ExpectedOutput(),
            difficulty="medium",
        )

        assert scenario.context == {"warehouse_id": "wh-001"}

    def test_invalid_difficulty(self) -> None:
        with pytest.raises(ValueError):
            EvaluationScenario(
                id="test_003",
                category="test",
                query="Test query",
                max_iterations=3,
                expected_output=ExpectedOutput(),
                difficulty="invalid",
            )

    def test_max_iterations_validation(self) -> None:
        with pytest.raises(ValueError):
            EvaluationScenario(
                id="test_004",
                category="test",
                query="Test query",
                max_iterations=0,
                expected_output=ExpectedOutput(),
                difficulty="easy",
            )

        with pytest.raises(ValueError):
            EvaluationScenario(
                id="test_005",
                category="test",
                query="Test query",
                max_iterations=11,
                expected_output=ExpectedOutput(),
                difficulty="easy",
            )


class TestEvaluationResult:
    """Tests for EvaluationResult model."""

    def test_valid_result(self) -> None:
        result = EvaluationResult(
            scenario_id="test_001",
            scenario_category="inventory",
            query="Test query",
            difficulty="easy",
            agent_status="completed",
            iterations=2,
            execution_time_seconds=5.5,
            retrieval_accuracy=0.9,
            citation_quality=0.8,
            code_validity=1.0,
            reasoning_quality=0.85,
            actionability=0.9,
            overall_score=0.87,
            passed=True,
        )

        assert result.scenario_id == "test_001"
        assert result.passed is True
        assert result.overall_score == 0.87
        assert isinstance(result.timestamp, datetime)

    def test_result_with_failures(self) -> None:
        result = EvaluationResult(
            scenario_id="test_002",
            scenario_category="supplier",
            query="Test query",
            difficulty="medium",
            agent_status="failed",
            iterations=0,
            execution_time_seconds=1.0,
            retrieval_accuracy=0.0,
            citation_quality=0.0,
            code_validity=0.0,
            reasoning_quality=0.0,
            actionability=0.0,
            overall_score=0.0,
            passed=False,
            failure_reasons=["Agent execution failed", "No data retrieved"],
        )

        assert result.passed is False
        assert len(result.failure_reasons) == 2

    def test_metric_bounds(self) -> None:
        with pytest.raises(ValueError):
            EvaluationResult(
                scenario_id="test_003",
                scenario_category="test",
                query="Test",
                difficulty="easy",
                agent_status="completed",
                iterations=1,
                execution_time_seconds=1.0,
                retrieval_accuracy=1.5,
                citation_quality=0.8,
                code_validity=1.0,
                reasoning_quality=0.8,
                actionability=0.8,
                overall_score=0.8,
                passed=True,
            )


class TestEvaluationReport:
    """Tests for EvaluationReport model."""

    def test_valid_report(self) -> None:
        results = [
            EvaluationResult(
                scenario_id="test_001",
                scenario_category="inventory",
                query="Query 1",
                difficulty="easy",
                agent_status="completed",
                iterations=2,
                execution_time_seconds=3.0,
                retrieval_accuracy=0.9,
                citation_quality=0.8,
                code_validity=1.0,
                reasoning_quality=0.85,
                actionability=0.9,
                overall_score=0.87,
                passed=True,
            ),
            EvaluationResult(
                scenario_id="test_002",
                scenario_category="supplier",
                query="Query 2",
                difficulty="medium",
                agent_status="completed",
                iterations=3,
                execution_time_seconds=5.0,
                retrieval_accuracy=0.8,
                citation_quality=0.7,
                code_validity=0.9,
                reasoning_quality=0.75,
                actionability=0.8,
                overall_score=0.79,
                passed=True,
            ),
        ]

        report = EvaluationReport(
            report_id="report_001",
            total_scenarios=2,
            passed=2,
            failed=0,
            pass_rate=1.0,
            avg_retrieval_accuracy=0.85,
            avg_citation_quality=0.75,
            avg_code_validity=0.95,
            avg_reasoning_quality=0.8,
            avg_actionability=0.85,
            avg_overall_score=0.83,
            avg_execution_time=4.0,
            avg_iterations=2.5,
            results=results,
        )

        assert report.total_scenarios == 2
        assert report.passed == 2
        assert report.pass_rate == 1.0
        assert len(report.results) == 2

    def test_report_with_category_stats(self) -> None:
        report = EvaluationReport(
            report_id="report_002",
            total_scenarios=3,
            passed=2,
            failed=1,
            pass_rate=0.67,
            avg_retrieval_accuracy=0.7,
            avg_citation_quality=0.6,
            avg_code_validity=0.8,
            avg_reasoning_quality=0.7,
            avg_actionability=0.75,
            avg_overall_score=0.71,
            avg_execution_time=3.5,
            avg_iterations=2.3,
            results_by_category={
                "inventory": CategoryStats(
                    total=2,
                    passed=2,
                    pass_rate=1.0,
                    avg_score=0.85,
                ),
                "supplier": CategoryStats(
                    total=1,
                    passed=0,
                    pass_rate=0.0,
                    avg_score=0.45,
                ),
            },
        )

        assert len(report.results_by_category) == 2
        assert report.results_by_category["inventory"].pass_rate == 1.0
        assert report.results_by_category["supplier"].pass_rate == 0.0
