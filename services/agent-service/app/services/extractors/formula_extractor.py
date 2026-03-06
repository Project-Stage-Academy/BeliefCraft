"""
Utilities for extracting mathematical formulas from text and RAG chunks.
"""

import re
from typing import Any

from app.models.responses import Formula
from app.services.extractors.tool_result_utils import extract_metadata, normalize_document
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
            document = normalize_document(chunk)
            if document is None:
                continue

            metadata = extract_metadata(document)
            chunk_type = str(metadata.get("type") or metadata.get("chunk_type") or "").lower()
            content = str(document.get("content") or "")

            # treats content as formula even if no $ delimiters
            if chunk_type in self._FORMULA_TYPES and content.strip():
                latex = (
                    content.strip()
                    if chunk_type == "numbered_formula"
                    else self._clean_latex(content)
                )
                formulas.append(
                    Formula(
                        latex=latex,
                        description=self._first_non_empty(metadata.get("description"))
                        or self._infer_description(content),
                    )
                )
                # Numbered formula chunks are already handled as standalone formulas.
                # Do not run generic embedded-LaTeX extraction on the same content.
                continue

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
    def _clean_latex(raw: str) -> str:
        # Keep delimiters/content intact and only normalize surrounding whitespace.
        # Delimiter stripping can corrupt multi-line LaTeX blocks that include
        # repeated $$ lines inside a single formula chunk.
        return raw.strip()

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
