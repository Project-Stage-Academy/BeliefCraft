import pytest
from pydantic import ValidationError
from rag_service.models import EntityType, SearchFilters
from retrieval.models import RAGTestCase, ScenarioVariant

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def baseline_variant() -> ScenarioVariant:
    return ScenarioVariant(variant="baseline")


@pytest.fixture()
def minimal_test_case(baseline_variant: ScenarioVariant) -> RAGTestCase:
    return RAGTestCase(
        id="tc_test_001",
        description="A minimal test case",
        base_query="What is a POMDP?",
        expected_chunk_ids=["uuid-001"],
        scenarios=[baseline_variant],
    )


# ---------------------------------------------------------------------------
# ScenarioVariant — happy paths
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "variant",
    [
        "baseline",  # pure semantic search
        "filtered",  # correct metadata filter applied
        "contradictory",  # mismatched filter → expect empty
    ],
)
def test_scenario_variant_accepts_all_valid_variant_values(variant: str) -> None:
    result = ScenarioVariant(variant=variant)

    assert result.variant == variant


def test_scenario_variant_baseline_has_correct_defaults() -> None:
    result = ScenarioVariant(variant="baseline")

    assert result.filters is None
    assert result.boost_params is None
    assert result.traverse_types is None
    assert result.expect_empty is False
    assert result.latency_budget_ms == 1000


def test_scenario_variant_stores_search_filters() -> None:
    filters = SearchFilters(part="I", section="3")

    result = ScenarioVariant(variant="filtered", filters=filters)

    assert result.filters is not None
    assert result.filters.part == "I"
    assert result.filters.section == "3"


def test_scenario_variant_contradictory_stores_expect_empty_flag() -> None:
    result = ScenarioVariant(variant="contradictory", expect_empty=True)

    assert result.expect_empty is True


def test_scenario_variant_stores_traverse_types() -> None:
    types = [EntityType.FORMULA, EntityType.ALGORITHM]

    result = ScenarioVariant(variant="baseline", traverse_types=types)

    assert result.traverse_types == [EntityType.FORMULA, EntityType.ALGORITHM]


def test_scenario_variant_stores_custom_latency_budget() -> None:
    result = ScenarioVariant(variant="baseline", latency_budget_ms=1500)

    assert result.latency_budget_ms == 1500


def test_scenario_variant_stores_boost_params() -> None:
    params = {"alpha": 0.7, "beta": 0.3}

    result = ScenarioVariant(variant="filtered", boost_params=params)

    assert result.boost_params == {"alpha": 0.7, "beta": 0.3}


# ---------------------------------------------------------------------------
# ScenarioVariant — edge cases & error states
# ---------------------------------------------------------------------------


def test_scenario_variant_invalid_variant_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        ScenarioVariant(variant="unknown")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "budget",
    [
        0,  # boundary — zero is not positive
        -1,  # negative
        -500,
    ],
)
def test_scenario_variant_non_positive_latency_budget_raises_validation_error(
    budget: int,
) -> None:
    with pytest.raises(ValidationError):
        ScenarioVariant(variant="baseline", latency_budget_ms=budget)


def test_scenario_variant_traverse_types_empty_list_is_valid() -> None:
    result = ScenarioVariant(variant="baseline", traverse_types=[])

    assert result.traverse_types == []


def test_scenario_variant_all_entity_types_accepted_in_traverse_types() -> None:
    all_types = list(EntityType)

    result = ScenarioVariant(variant="baseline", traverse_types=all_types)

    assert result.traverse_types == all_types


# ---------------------------------------------------------------------------
# RAGTestCase — happy paths
# ---------------------------------------------------------------------------


def test_rag_test_case_creates_with_all_fields(baseline_variant: ScenarioVariant) -> None:
    tc = RAGTestCase(
        id="tc_belief_update",
        description="Belief update via Bayes rule",
        base_query="How does Bayesian belief update work in a POMDP?",
        expected_chunk_ids=["uuid-abc", "uuid-def"],
        scenarios=[baseline_variant],
        expected_metadata={"chunk_type": "text", "part": "I"},
        domain="book",
    )

    assert tc.id == "tc_belief_update"
    assert tc.base_query == "How does Bayesian belief update work in a POMDP?"
    assert len(tc.expected_chunk_ids) == 2
    assert tc.domain == "book"


@pytest.mark.parametrize(
    "domain",
    [
        "book",  # standard book knowledge
        "warehouse",  # warehouse simulation domain
        "cross_domain",  # cross-domain link pointer
    ],
)
def test_rag_test_case_accepts_all_valid_domains(
    domain: str, baseline_variant: ScenarioVariant
) -> None:
    tc = RAGTestCase(
        id="tc_x",
        description="domain test",
        base_query="query",
        expected_chunk_ids=["uuid-001"],
        scenarios=[baseline_variant],
        domain=domain,  # type: ignore[arg-type]
    )

    assert tc.domain == domain


def test_rag_test_case_domain_defaults_to_book(baseline_variant: ScenarioVariant) -> None:
    tc = RAGTestCase(
        id="tc_x",
        description="desc",
        base_query="q",
        expected_chunk_ids=["uuid-001"],
        scenarios=[baseline_variant],
    )

    assert tc.domain == "book"


def test_rag_test_case_expected_metadata_defaults_to_empty_dict(
    baseline_variant: ScenarioVariant,
) -> None:
    tc = RAGTestCase(
        id="tc_x",
        description="desc",
        base_query="q",
        expected_chunk_ids=["uuid-001"],
        scenarios=[baseline_variant],
    )

    assert tc.expected_metadata == {}


def test_rag_test_case_empty_expected_chunk_ids_is_valid(
    baseline_variant: ScenarioVariant,
) -> None:
    tc = RAGTestCase(
        id="tc_x",
        description="desc",
        base_query="q",
        expected_chunk_ids=[],
        scenarios=[baseline_variant],
    )

    assert tc.expected_chunk_ids == []


def test_rag_test_case_stores_multiple_scenarios() -> None:
    variants = [
        ScenarioVariant(variant="baseline"),
        ScenarioVariant(variant="filtered", filters=SearchFilters(part="II")),
        ScenarioVariant(variant="contradictory", expect_empty=True),
    ]

    tc = RAGTestCase(
        id="tc_multi",
        description="multi scenario",
        base_query="entropy in decision making",
        expected_chunk_ids=["uuid-001"],
        scenarios=variants,
    )

    assert len(tc.scenarios) == 3
    assert tc.scenarios[0].variant == "baseline"
    assert tc.scenarios[1].variant == "filtered"
    assert tc.scenarios[2].variant == "contradictory"


def test_rag_test_case_expected_metadata_is_independent_per_instance(
    baseline_variant: ScenarioVariant,
) -> None:
    tc1 = RAGTestCase(
        id="tc_1",
        description="d",
        base_query="q",
        expected_chunk_ids=[],
        scenarios=[baseline_variant],
    )
    tc2 = RAGTestCase(
        id="tc_2",
        description="d",
        base_query="q",
        expected_chunk_ids=[],
        scenarios=[baseline_variant],
    )

    tc1.expected_metadata["key"] = "value"

    assert "key" not in tc2.expected_metadata


# ---------------------------------------------------------------------------
# RAGTestCase — error states
# ---------------------------------------------------------------------------


def test_rag_test_case_invalid_domain_raises_validation_error(
    baseline_variant: ScenarioVariant,
) -> None:
    with pytest.raises(ValidationError):
        RAGTestCase(
            id="tc_x",
            description="desc",
            base_query="q",
            expected_chunk_ids=["uuid-001"],
            scenarios=[baseline_variant],
            domain="unknown_domain",  # type: ignore[arg-type]
        )


def test_rag_test_case_missing_required_fields_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        RAGTestCase(  # type: ignore[call-arg]
            id="tc_x",
        )


# ---------------------------------------------------------------------------
# RAGTestCase — paraphrases field
# ---------------------------------------------------------------------------


def test_rag_test_case_paraphrases_defaults_to_empty_list(
    baseline_variant: ScenarioVariant,
) -> None:
    tc = RAGTestCase(
        id="tc_x",
        description="d",
        base_query="q",
        expected_chunk_ids=["uuid-001"],
        scenarios=[baseline_variant],
    )

    assert tc.paraphrases == []


def test_rag_test_case_stores_paraphrases(baseline_variant: ScenarioVariant) -> None:
    phrases = ["How does X work?", "Explain X in detail."]

    tc = RAGTestCase(
        id="tc_x",
        description="d",
        base_query="What is X?",
        expected_chunk_ids=["uuid-001"],
        scenarios=[baseline_variant],
        paraphrases=phrases,
    )

    assert tc.paraphrases == phrases


def test_rag_test_case_paraphrases_are_independent_per_instance(
    baseline_variant: ScenarioVariant,
) -> None:
    tc1 = RAGTestCase(
        id="tc_1",
        description="d",
        base_query="q",
        expected_chunk_ids=[],
        scenarios=[baseline_variant],
    )
    tc2 = RAGTestCase(
        id="tc_2",
        description="d",
        base_query="q",
        expected_chunk_ids=[],
        scenarios=[baseline_variant],
    )

    tc1.paraphrases.append("extra")

    assert "extra" not in tc2.paraphrases


# ---------------------------------------------------------------------------
# RAGTestCase — split field
# ---------------------------------------------------------------------------


def test_rag_test_case_split_defaults_to_none(baseline_variant: ScenarioVariant) -> None:
    tc = RAGTestCase(
        id="tc_x",
        description="d",
        base_query="q",
        expected_chunk_ids=["uuid-001"],
        scenarios=[baseline_variant],
    )

    assert tc.split is None


@pytest.mark.parametrize(
    "split",
    [
        "validation",  # used during experiments
        "test",  # evaluated only at cycle end
    ],
)
def test_rag_test_case_accepts_valid_split_values(
    split: str, baseline_variant: ScenarioVariant
) -> None:
    tc = RAGTestCase(
        id="tc_x",
        description="d",
        base_query="q",
        expected_chunk_ids=["uuid-001"],
        scenarios=[baseline_variant],
        split=split,  # type: ignore[arg-type]
    )

    assert tc.split == split


def test_rag_test_case_invalid_split_raises_validation_error(
    baseline_variant: ScenarioVariant,
) -> None:
    with pytest.raises(ValidationError):
        RAGTestCase(
            id="tc_x",
            description="d",
            base_query="q",
            expected_chunk_ids=["uuid-001"],
            scenarios=[baseline_variant],
            split="train",  # type: ignore[arg-type]
        )
