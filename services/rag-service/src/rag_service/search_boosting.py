from typing import Any

from .models import Document, SearchTags


class SearchResultBooster:
    """Apply optional search-tag boosting and stable reranking to root documents."""

    _CONCEPT_MATCH_BONUS = 0.1
    _DB_TABLE_MATCH_BONUS = 0.1

    def __init__(self, search_tags: SearchTags | None, k: int) -> None:
        self._search_tags = search_tags
        self._k = k

    def candidate_limit_for_boosting(self) -> int:
        """Return candidate pool size used before optional boosted reranking."""
        if self._search_tags is None:
            return self._k
        if not self._search_tags.bc_concepts and not self._search_tags.bc_db_tables:
            return self._k
        return self._k + 10

    def apply(self, documents: list[Document]) -> list[Document]:
        """Return top-k reranked documents, with boosting when tags are provided."""
        search_tags = self._search_tags
        if search_tags is None:
            return documents[: self._k]
        if not search_tags.bc_concepts and not search_tags.bc_db_tables:
            return documents[: self._k]

        boosted_documents = [
            document.model_copy(
                update={"cosine_similarity": self._boost_score(document, search_tags)}
            )
            for document in documents
        ]

        scored_documents = [
            (
                idx,
                document.cosine_similarity if document.cosine_similarity is not None else 0.0,
                document,
            )
            for idx, document in enumerate(boosted_documents)
        ]
        scored_documents.sort(key=lambda item: (-item[1], item[0]))
        return [document for _, _, document in scored_documents][: self._k]

    @staticmethod
    def deduplicate_documents(documents: list[Document]) -> list[Document]:
        """Deduplicate by id while preserving first-seen order."""
        unique_documents: list[Document] = []
        seen_ids: set[str] = set()

        for document in documents:
            document_id = document.id
            if document_id is None:
                unique_documents.append(document)
                continue
            if document_id in seen_ids:
                continue
            seen_ids.add(document_id)
            unique_documents.append(document)

        return unique_documents

    @classmethod
    def _boost_score(cls, document: Document, search_tags: SearchTags) -> float:
        metadata = document.metadata or {}
        doc_concepts = cls._to_string_set(metadata.get("bc_concepts"))
        doc_tables = cls._to_string_set(metadata.get("bc_db_tables"))

        concept_overlap = len(doc_concepts.intersection(set(search_tags.bc_concepts)))
        table_overlap = len(doc_tables.intersection(set(search_tags.bc_db_tables)))

        base_similarity = (
            document.cosine_similarity if document.cosine_similarity is not None else 0.0
        )
        boosted_similarity = (
            base_similarity
            + (concept_overlap * cls._CONCEPT_MATCH_BONUS)
            + (table_overlap * cls._DB_TABLE_MATCH_BONUS)
        )
        return min(boosted_similarity, 1.0)

    @staticmethod
    def _to_string_set(values: Any) -> set[str]:
        if not isinstance(values, list):
            return set()
        return {value for value in values if isinstance(value, str)}
