"""
Utilities for extracting mathematical formulas from text and RAG chunks.
"""

import re
from typing import Any

from app.models.responses import Formula
from common.logging import get_logger

logger = get_logger(__name__)


class FormulaExtractor:
    """
    Extract and normalize mathematical formulas from text and RAG chunks.

    Supports:
    - LaTeX blocks in plain text
    - Formula-typed RAG chunks (metadata-driven)
    - Deduplication by normalized LaTeX content
    """

    LATEX_PATTERNS = [
        re.compile(r"\$\$(.*?)\$\$", re.DOTALL),
        re.compile(r"\\begin\{equation\*?\}(.*?)\\end\{equation\*?\}", re.DOTALL),
        re.compile(r"\\begin\{align\*?\}(.*?)\\end\{align\*?\}", re.DOTALL),
        re.compile(r"(?<!\$)\$(?!\$)(.*?)(?<!\$)\$(?!\$)", re.DOTALL),
    ]

    _FORMULA_TYPES = {"formula", "numbered_formula"}

    def extract_from_text(self, text: str) -> list[Formula]:
        """
        Extracts LaTeX formulas from arbitrary text.
        """
        if not text:
            return []

        formulas: list[Formula] = []
        for pattern in self.LATEX_PATTERNS:
            for raw_match in pattern.findall(text):
                latex = self._clean_latex(raw_match)
                if not self._is_meaningful_formula(latex):
                    continue
                formulas.append(
                    Formula(
                        latex=latex,
                        description=self._infer_description(latex),
                    )
                )

        deduplicated = self._deduplicate(formulas)
        logger.info(
            "formulas_extracted_from_text",
            total_found=len(formulas),
            deduplicated_count=len(deduplicated),
        )
        return deduplicated

    def extract_from_rag_chunks(self, chunks: list[dict[str, Any]]) -> list[Formula]:
        """
        Extracts formulas from RAG chunks.

        Supports both common result shapes:
        - {"content": "...", "metadata": {...}}
        - {"content": "...", "chunk_type": "...", "type": "...", ...}
        """
        formulas: list[Formula] = []

        for chunk in chunks:
            metadata = self._extract_metadata(chunk)
            chunk_type = str(
                metadata.get("type")
                or metadata.get("chunk_type")
                or chunk.get("type")
                or chunk.get("chunk_type")
                or ""
            ).lower()
            content = str(chunk.get("content") or "")

            # treats content as formula even if no $ delimiters
            if chunk_type in self._FORMULA_TYPES and content.strip():
                formulas.append(
                    Formula(
                        latex=self._clean_latex(content),
                        description=self._first_non_empty(
                            metadata.get("description"),
                            chunk.get("description"),
                            metadata.get("section_title"),
                            metadata.get("subsection_title"),
                        )
                        or self._infer_description(content),
                        variables=self._normalize_variables(
                            metadata.get("variables") or chunk.get("variables")
                        ),
                    )
                )

            # also parses embedded LaTeX in all chunk contents
            formulas.extend(self.extract_from_text(content))

        deduplicated = self._deduplicate(formulas)
        logger.info(
            "formulas_extracted_from_rag_chunks",
            chunk_count=len(chunks),
            total_found=len(formulas),
            deduplicated_count=len(deduplicated),
        )
        return deduplicated

    @staticmethod
    def _extract_metadata(chunk: dict[str, Any]) -> dict[str, Any]:
        metadata = chunk.get("metadata")
        if isinstance(metadata, dict):
            return metadata
        return {}

    @staticmethod
    def _clean_latex(raw: str) -> str:
        latex = raw.strip()
        # normalizes common math delimiters so formula chunks and text extraction
        # produces the same canonical form for deduplication.
        if latex.startswith("$$") and latex.endswith("$$") and len(latex) >= 4:
            return latex[2:-2].strip()
        if latex.startswith("$") and latex.endswith("$") and len(latex) >= 2:
            return latex[1:-1].strip()
        return latex

    @staticmethod
    def _is_meaningful_formula(latex: str) -> bool:
        # short formulas like "x=1"
        return bool(latex and len(latex) >= 3)

    @staticmethod
    def _normalize_formula_key(latex: str) -> str:
        return re.sub(r"\s+", "", latex)

    def _deduplicate(self, formulas: list[Formula]) -> list[Formula]:
        seen: set[str] = set()
        deduplicated: list[Formula] = []
        for formula in formulas:
            key = self._normalize_formula_key(formula.latex)
            if key in seen:
                continue
            seen.add(key)
            deduplicated.append(formula)
        return deduplicated

    @staticmethod
    def _normalize_variables(raw_variables: Any) -> dict[str, str] | None:
        if not isinstance(raw_variables, dict):
            return None
        normalized = {str(k): str(v) for k, v in raw_variables.items()}
        return normalized or None

    @staticmethod
    def _first_non_empty(*values: Any) -> str | None:
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _infer_description(self, latex: str) -> str:
        """
        Infer a coarse formula description using lightweight heuristics.
        """
        normalized = latex.lower()
        if "p(" in normalized or "pr(" in normalized:
            return "Probability expression"
        if "\\sum" in normalized:
            return "Summation expression"
        if "\\int" in normalized:
            return "Integral expression"
        if "\\frac" in normalized:
            return "Fraction or ratio expression"
        if "=" in normalized:
            return "Equation"
        return "Mathematical expression"
