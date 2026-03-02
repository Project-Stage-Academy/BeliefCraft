"""
Utilities for extracting and enriching code snippets from agent output and RAG chunks.
"""

import ast
import re
from typing import Any

from app.models.responses import CodeSnippet
from app.services.extractors.tool_result_utils import (
    collect_result_documents,
    extract_metadata,
    is_rag_tool_call,
    tool_call_field,
)
from common.logging import get_logger

logger = get_logger(__name__)


class CodeExtractor:
    """
    Extract code snippets from final answers and RAG tool outputs.

    Behavior:
    - Parses fenced markdown code blocks
    - Reads code-like fields from RAG documents
    - Infers language when not explicitly provided
    - Validates Python snippets with AST and detects dependencies
    - Deduplicates snippets by language + normalized code content
    """

    _RAG_CODE_CHUNK_TYPES = {"algorithm", "algorithm_code"}
    _CODE_BLOCK_PATTERN = re.compile(
        r"```(?P<lang>[a-zA-Z0-9_+-]*)\n(?P<code>.*?)```",
        re.DOTALL,
    )

    def extract_from_answer_and_tool_calls(
        self,
        final_answer: str,
        tool_calls: list[Any],
    ) -> list[CodeSnippet]:
        """
        Extract code snippets from final answer text and RAG tool results.
        """
        snippets: list[CodeSnippet] = []
        snippets.extend(self.extract_from_text(final_answer))

        for tool_call in tool_calls:
            if not is_rag_tool_call(tool_call):
                continue

            result = tool_call_field(tool_call, "result")
            for document in collect_result_documents(result):
                snippets.extend(self.extract_from_document(document))

        deduplicated = self._deduplicate_code_snippets(snippets)
        logger.info(
            "code_snippets_extracted",
            total_found=len(snippets),
            deduplicated_count=len(deduplicated),
        )
        return deduplicated

    def extract_from_text(self, text: str) -> list[CodeSnippet]:
        """
        Extract fenced markdown code blocks from arbitrary text.
        """
        if not text:
            return []

        snippets: list[CodeSnippet] = []
        for match in self._CODE_BLOCK_PATTERN.finditer(text):
            raw_code = match.group("code")
            language_hint = match.group("lang")
            snippet = self._build_code_snippet(raw_code, language_hint=language_hint)
            if snippet is not None:
                snippets.append(snippet)

        return snippets

    def extract_from_document(self, document: dict[str, Any]) -> list[CodeSnippet]:
        """
        Extract snippets from a single RAG document-like object.
        """
        metadata = extract_metadata(document)
        description = self._first_non_empty(
            metadata.get("section_title"),
            document.get("section_title"),
            metadata.get("algorithm_name"),
            document.get("algorithm_name"),
            metadata.get("title"),
            document.get("title"),
        )

        snippets: list[CodeSnippet] = []

        # Prefer explicit code fields when available.
        candidates: list[tuple[Any, str]] = [
            (metadata.get("code_snippet_python"), "python"),
            (document.get("code_snippet_python"), "python"),
            (metadata.get("code_language_translated"), "python"),
            (document.get("code_language_translated"), "python"),
            (metadata.get("code_snippet_julia"), "julia"),
            (document.get("code_snippet_julia"), "julia"),
        ]

        for raw_code, language_hint in candidates:
            if not isinstance(raw_code, str) or not raw_code.strip():
                continue
            snippet = self._build_code_snippet(
                raw_code,
                language_hint=language_hint,
                description=description,
            )
            if snippet is not None:
                snippets.append(snippet)

        chunk_type = self._first_non_empty(
            metadata.get("chunk_type"),
            metadata.get("type"),
            document.get("chunk_type"),
            document.get("type"),
        )
        content = document.get("content")

        if (
            isinstance(content, str)
            and content.strip()
            and isinstance(chunk_type, str)
            and chunk_type.lower() in self._RAG_CODE_CHUNK_TYPES
        ):
            snippet = self._build_code_snippet(
                content,
                language_hint=None,
                description=description,
            )
            if snippet is not None:
                snippets.append(snippet)

        if isinstance(content, str) and content.strip():
            fenced = self.extract_from_text(content)
            for snippet in fenced:
                if not snippet.description and description:
                    snippet.description = description
            snippets.extend(fenced)

        return self._deduplicate_code_snippets(snippets)

    def _build_code_snippet(
        self,
        code: str,
        language_hint: str | None,
        description: str | None = None,
    ) -> CodeSnippet | None:
        normalized_code = code.strip()
        if not normalized_code:
            return None

        language = self._normalize_code_language(language_hint, normalized_code)
        validated = False
        dependencies: list[str] = []

        if language == "python":
            try:
                ast.parse(normalized_code)
            except SyntaxError:
                logger.warning("invalid_python_snippet_downgraded_to_text")
                language = "text"
            else:
                validated = True
                dependencies = self._detect_python_dependencies(normalized_code)

        return CodeSnippet(
            language=language,
            code=normalized_code,
            description=description,
            dependencies=dependencies,
            validated=validated,
        )

    @staticmethod
    def _normalize_code_language(language_hint: str | None, code: str) -> str:
        hint = (language_hint or "").strip().lower()
        if hint in {"python", "py"}:
            return "python"
        if hint in {"julia", "jl"}:
            return "julia"
        if hint in {"text", "txt", "plain", "plaintext"}:
            return "text"

        if re.search(
            r"^\s*(from\s+\w+\s+import|import\s+\w+|def\s+\w+\s*\()",
            code,
            re.MULTILINE,
        ):
            return "python"
        if re.search(r"^\s*function\s+\w+", code, re.MULTILINE) and re.search(
            r"\bend\b",
            code,
            re.MULTILINE,
        ):
            return "julia"

        try:
            ast.parse(code)
            return "python"
        except SyntaxError:
            return "text"

    @staticmethod
    def _detect_python_dependencies(code: str) -> list[str]:
        dependencies: set[str] = set()
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    dependencies.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                dependencies.add(node.module.split(".")[0])

        return sorted(dependencies)

    @staticmethod
    def _first_non_empty(*values: Any) -> str | None:
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _deduplicate_code_snippets(snippets: list[CodeSnippet]) -> list[CodeSnippet]:
        seen: set[tuple[str, str]] = set()
        deduplicated: list[CodeSnippet] = []

        for snippet in snippets:
            key = (
                snippet.language.strip().lower(),
                re.sub(r"\s+", " ", snippet.code).strip(),
            )
            if key in seen:
                continue
            seen.add(key)
            deduplicated.append(snippet)

        return deduplicated
