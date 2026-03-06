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
    normalize_document,
    tool_call_field,
)
from common.logging import get_logger

logger = get_logger(__name__)


class CodeExtractor:
    """
    Extract code snippets from final answers and RAG tool outputs.

    Behavior:
    - Parses fenced markdown code blocks
    - Reads code from RAG algorithm document content
    - Infers language for free-form markdown code blocks
    - Treats RAG code payloads as Python-by-contract
    - Validates Python snippets with AST and detects dependencies
    - Deduplicates snippets by language + normalized code content
    """

    _RAG_CODE_CHUNK_TYPES = {"algorithm"}
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
        canonical_document = normalize_document(document)
        if canonical_document is None:
            return []

        metadata = extract_metadata(canonical_document)
        description = self._first_non_empty(
            metadata.get("section_title"),
            metadata.get("algorithm_name"),
            metadata.get("title"),
        )

        snippets: list[CodeSnippet] = []
        declared_dependencies = self._extract_declared_dependencies(metadata)

        chunk_type = self._first_non_empty(
            metadata.get("chunk_type"),
            metadata.get("type"),
        )
        content = canonical_document.get("content")

        if (
            isinstance(content, str)
            and content.strip()
            and isinstance(chunk_type, str)
            and chunk_type.lower() in self._RAG_CODE_CHUNK_TYPES
        ):
            snippet = self._build_rag_code_snippet(
                content,
                description=description,
                declared_dependencies=declared_dependencies,
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

    def _build_rag_code_snippet(
        self,
        code: str,
        description: str | None = None,
        declared_dependencies: list[str] | None = None,
    ) -> CodeSnippet | None:
        """
        Build a snippet from RAG payload.

        RAG contract currently returns Python code only. We still AST-validate and
        downgrade invalid code to `text` for safety.
        """
        normalized_code = code.strip()
        if not normalized_code:
            return None

        syntax_valid = False
        language = "python"
        dependencies: list[str] = []

        try:
            ast.parse(normalized_code)
        except SyntaxError:
            logger.warning("invalid_rag_python_snippet_downgraded_to_text")
            language = "text"
        else:
            syntax_valid = True
            if declared_dependencies:
                dependencies = declared_dependencies
            else:
                dependencies = self._detect_python_dependencies(normalized_code)

        return CodeSnippet(
            language=language,
            code=normalized_code,
            description=description,
            dependencies=dependencies,
            validated=syntax_valid,
        )

    @staticmethod
    def _extract_declared_dependencies(metadata: dict[str, Any]) -> list[str]:
        """
        Extract package dependencies declared by RAG metadata.

        Accepted keys:
        - dependencies
        - python_dependencies
        - required_packages
        """
        raw = (
            metadata.get("dependencies")
            or metadata.get("python_dependencies")
            or metadata.get("required_packages")
        )

        if raw is None:
            return []

        if isinstance(raw, str):
            items = [raw]
        elif isinstance(raw, (list, tuple, set)):
            items = [item for item in raw if isinstance(item, str)]
        else:
            return []

        normalized: set[str] = set()
        for item in items:
            for token in item.split(","):
                dep = token.strip()
                if dep:
                    normalized.add(dep)

        return sorted(normalized)

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
        syntax_valid = False
        dependencies: list[str] = []

        if language == "python":
            try:
                ast.parse(normalized_code)
            except SyntaxError:
                logger.warning("invalid_python_snippet_downgraded_to_text")
                language = "text"
            else:
                syntax_valid = True
                dependencies = self._detect_python_dependencies(normalized_code)

        return CodeSnippet(
            language=language,
            code=normalized_code,
            description=description,
            dependencies=dependencies,
            validated=syntax_valid,
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
