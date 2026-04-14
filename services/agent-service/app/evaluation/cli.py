"""CLI for running agent evaluations."""

import asyncio
import json
from pathlib import Path

import click
from app.evaluation.evaluator import AgentEvaluator
from common.logging import configure_logging, get_logger

configure_logging(service_name="agent-evaluation")
logger = get_logger(__name__)


@click.group()
def cli() -> None:
    """Agent Evaluation CLI."""
    pass


@cli.command()
@click.option(
    "--scenarios",
    "-s",
    multiple=True,
    help="Specific scenario IDs to run (can be specified multiple times)",
)
@click.option(
    "--output",
    "-o",
    default="evaluation_report.json",
    help="Output file for JSON report",
)
@click.option(
    "--scenarios-file",
    "-f",
    type=click.Path(exists=True),
    help="Path to scenarios YAML file (defaults to app/evaluation/test_scenarios.yaml)",
)
def run(scenarios: tuple[str, ...], output: str, scenarios_file: str | None) -> None:
    """
    Run agent evaluation.

    Examples:
        uv run python -m app.evaluation.cli run
        uv run python -m app.evaluation.cli run -s scenario_001_inventory_low_stock
        uv run python -m app.evaluation.cli run -s scenario_001 -s scenario_002 -o report.json
    """
    click.echo("=" * 70)
    click.echo("Agent Evaluation Framework")
    click.echo("=" * 70)

    evaluator = AgentEvaluator(scenarios_path=scenarios_file)

    scenario_ids = list(scenarios) if scenarios else None

    if scenario_ids:
        click.echo(f"\nRunning {len(scenario_ids)} specific scenario(s)...")
    else:
        click.echo(f"\nRunning all {len(evaluator.scenarios)} scenarios...")

    click.echo()

    report = asyncio.run(evaluator.run_evaluation(scenario_ids))

    click.echo("\n" + "=" * 70)
    click.echo("EVALUATION REPORT")
    click.echo("=" * 70)
    click.echo(f"\nReport ID: {report.report_id}")
    click.echo(f"Total Scenarios: {report.total_scenarios}")
    click.echo(f"Passed: {report.passed} ({report.pass_rate * 100:.1f}%) | Failed: {report.failed}")

    click.echo("\nAverage Scores:")
    click.echo(f"  Retrieval Accuracy:  {report.avg_retrieval_accuracy:.2f}")
    click.echo(f"  Citation Quality:    {report.avg_citation_quality:.2f}")
    click.echo(f"  Code Validity:       {report.avg_code_validity:.2f}")
    click.echo(f"  Reasoning Quality:   {report.avg_reasoning_quality:.2f}")
    click.echo(f"  Actionability:       {report.avg_actionability:.2f}")
    click.echo(f"  Overall Score:       {report.avg_overall_score:.2f}")

    click.echo("\nPerformance:")
    click.echo(f"  Avg Execution Time:  {report.avg_execution_time:.1f}s")
    click.echo(f"  Avg Iterations:      {report.avg_iterations:.1f}")

    click.echo("\nResults by Category:")
    for category, stats in report.results_by_category.items():
        click.echo(
            f"  {category:30s} | Pass: {stats.pass_rate * 100:5.1f}% | Score: {stats.avg_score:.2f}"
        )

    click.echo("\nResults by Difficulty:")
    for difficulty, stats in report.results_by_difficulty.items():
        click.echo(
            f"  {difficulty:10s} | "
            f"Pass: {stats.pass_rate * 100:5.1f}% | "
            f"Score: {stats.avg_score:.2f}"
        )

    if report.failed_scenarios:
        click.echo("\nFailed Scenarios:")
        for scenario_id in report.failed_scenarios:
            result = next(r for r in report.results if r.scenario_id == scenario_id)
            click.echo(f"  - {scenario_id}")
            for reason in result.failure_reasons:
                click.echo(f"    → {reason}")

    output_path = Path(output)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report.model_dump(), f, indent=2, default=str)

    click.echo(f"\n✓ Full report saved to: {output_path}")
    click.echo("=" * 70)


@cli.command(name="list")
@click.option(
    "--scenarios-file",
    "-f",
    type=click.Path(exists=True),
    help="Path to scenarios YAML file",
)
def list_scenarios(scenarios_file: str | None) -> None:
    """
    List all available evaluation scenarios.

    Example:
        uv run python -m app.evaluation.cli list
    """
    evaluator = AgentEvaluator(scenarios_path=scenarios_file)

    click.echo("=" * 70)
    click.echo("Available Evaluation Scenarios")
    click.echo("=" * 70)
    click.echo(f"\nTotal: {len(evaluator.scenarios)} scenarios")
    click.echo()

    from app.evaluation.models import EvaluationScenario

    by_difficulty: dict[str, list[EvaluationScenario]] = {
        "easy": [],
        "medium": [],
        "hard": [],
    }

    for scenario in evaluator.scenarios:
        by_difficulty[scenario.difficulty].append(scenario)

    for difficulty in ["easy", "medium", "hard"]:
        scenarios_list = by_difficulty[difficulty]
        click.echo(f"{difficulty.upper()} ({len(scenarios_list)} scenarios):")

        for scenario in scenarios_list:
            click.echo(f"  [{scenario.id}]")
            click.echo(f"    Category: {scenario.category}")
            click.echo(f"    Max Iterations: {scenario.max_iterations}")
            click.echo(
                f"    Query: {scenario.query[:80]}{'...' if len(scenario.query) > 80 else ''}"
            )
            click.echo()

    click.echo("=" * 70)


@cli.command()
@click.argument("scenario_id")
@click.option(
    "--scenarios-file",
    "-f",
    type=click.Path(exists=True),
    help="Path to scenarios YAML file",
)
def show(scenario_id: str, scenarios_file: str | None) -> None:
    """
    Show detailed information for a specific scenario.

    Example:
        uv run python -m app.evaluation.cli show scenario_001_inventory_low_stock
    """
    evaluator = AgentEvaluator(scenarios_path=scenarios_file)

    scenario = next((s for s in evaluator.scenarios if s.id == scenario_id), None)

    if not scenario:
        click.echo(f"Error: Scenario '{scenario_id}' not found", err=True)
        raise SystemExit(1)

    click.echo("=" * 70)
    click.echo(f"Scenario: {scenario.id}")
    click.echo("=" * 70)
    click.echo(f"\nCategory:       {scenario.category}")
    click.echo(f"Difficulty:     {scenario.difficulty}")
    click.echo(f"Max Iterations: {scenario.max_iterations}")
    click.echo(f"\nQuery:\n  {scenario.query}")

    if scenario.context:
        click.echo("\nContext:")
        for key, value in scenario.context.items():
            click.echo(f"  {key}: {value}")

    click.echo("\nExpected Output:")
    for key, value in scenario.expected_output.must_include.items():
        click.echo(f"  must_include.{key}: {value}")

    if scenario.expected_output.must_cite:
        for key, value in scenario.expected_output.must_cite.items():
            click.echo(f"  must_cite.{key}: {value}")

    if scenario.evaluation_criteria:
        click.echo("\nEvaluation Criteria:")
        for key, value in scenario.evaluation_criteria.items():
            click.echo(f"  {key}: {value}")

    click.echo("=" * 70)


if __name__ == "__main__":
    cli()
