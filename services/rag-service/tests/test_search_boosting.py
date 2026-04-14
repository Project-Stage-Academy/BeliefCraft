import pytest
from rag_service.models import Document, SearchTags
from rag_service.search_boosting import SearchResultBooster


def test_candidate_limit_for_boosting_uses_wider_pool_for_non_empty_tags() -> None:
    tags = SearchTags(bc_concepts=["MULTI_AGENT_COORDINATION"], bc_db_tables=[])

    candidate_limit = SearchResultBooster(tags, 5).candidate_limit_for_boosting()

    assert candidate_limit == 15


def test_candidate_limit_for_boosting_keeps_k_for_empty_tags() -> None:
    candidate_limit = SearchResultBooster(SearchTags(), 5).candidate_limit_for_boosting()

    assert candidate_limit == 5


def test_apply_boosts_and_reranks_documents() -> None:
    documents = [
        Document(
            id="doc-low",
            content="low",
            cosine_similarity=0.8,
            metadata={"bc_concepts": [], "bc_db_tables": []},
        ),
        Document(
            id="doc-mid",
            content="mid",
            cosine_similarity=0.8,
            metadata={"bc_concepts": ["MULTI_AGENT_COORDINATION"], "bc_db_tables": []},
        ),
        Document(
            id="doc-high",
            content="high",
            cosine_similarity=0.8,
            metadata={
                "bc_concepts": ["MULTI_AGENT_COORDINATION"],
                "bc_db_tables": ["observations"],
            },
        ),
    ]

    boosted = SearchResultBooster(
        SearchTags(
            bc_concepts=["MULTI_AGENT_COORDINATION"],
            bc_db_tables=["observations"],
        ),
        3,
    ).apply(documents)

    assert [doc.id for doc in boosted] == ["doc-high", "doc-mid", "doc-low"]
    assert boosted[0].cosine_similarity == pytest.approx(1.0)
    assert boosted[1].cosine_similarity == pytest.approx(0.9)


def test_apply_preserves_order_when_tags_are_missing() -> None:
    documents = [
        Document(id="doc-1", content="1", cosine_similarity=0.7),
        Document(id="doc-2", content="2", cosine_similarity=0.7),
    ]

    boosted = SearchResultBooster(None, 2).apply(documents)

    assert [doc.id for doc in boosted] == ["doc-1", "doc-2"]


def test_deduplicate_documents_keeps_first_seen_order() -> None:
    documents = [
        Document(id="doc-1", content="root"),
        Document(id="doc-1", content="duplicate"),
        Document(id="doc-2", content="expanded"),
        Document(id=None, content="without-id"),
    ]

    deduplicated = SearchResultBooster.deduplicate_documents(documents)

    assert [doc.id for doc in deduplicated] == ["doc-1", "doc-2", None]
