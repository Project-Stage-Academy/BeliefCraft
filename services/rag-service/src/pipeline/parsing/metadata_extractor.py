import re
from typing import Any


class MetadataExtractor:
    """
    Class for tracking and extracting hierarchical document metadata and references.
    Maintains state of current section, subsection, and subsubsection levels.
    """

    def __init__(self) -> None:
        self.current_section_title: str | None = None
        self.current_section_num: str | None = None
        self.current_subsection_title: str | None = None
        self.current_subsection_num: str | None = None
        self.current_subsubsection_title: str | None = None
        self.current_subsubsection_num: str | None = None

    def process_content_and_get_meta(self, content: str) -> dict[str, Any]:
        """
        Analyzes raw text to detect headers and update the current hierarchy state.
        Filters out metadata-only lines (like page numbers) from the clean content.

        Args:
            content (str): Raw text block from a document page.

        Returns:
            dict: Current metadata state including cleaned text and a 'force_new_chunk' flag.
        """
        if not content:
            return self._get_current_dict("")

        lines = content.split("\n")
        clean_lines: list[str] = []
        force_new_chunk = False

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # 1. SECTION (e.g., CHAPTER 1 INTRODUCTION)
            sec_match = re.match(r"^(?:##\s+)?(?:CHAPTER\s+)?(\d+)\s+([A-Z\s]{3,})", stripped, re.I)
            if sec_match:
                self.current_section_num = sec_match.group(1)
                self.current_section_title = (
                    f"{self.current_section_num} {sec_match.group(2).strip()}".upper()
                )
                self._reset_lower_levels()
                force_new_chunk = True
                continue

            # 2. SUBSECTION (e.g., 1.1 Fundamental Concepts)
            subsec_match = re.match(
                r"^(?:###\s+)?(\d+\.\d+)\.?\s+([A-Z][A-Za-z\s\-\:\,]+)", stripped
            )
            if subsec_match:
                self.current_subsection_num = subsec_match.group(1)
                self.current_subsection_title = (
                    f"{self.current_subsection_num} {subsec_match.group(2).strip()}"
                )
                self.current_subsubsection_title = None
                self.current_subsubsection_num = None
                force_new_chunk = True
                continue

            # 3. SUBSUBSECTION (e.g., 1.1.1 Definitions or Exercise 1.1)
            subsub_match = re.match(
                r"^(?:####\s+)?(\d+\.\d+\.\d+|Exercise\s+\d+\.\d+)\s*([A-Z][A-Za-z\s\-\:\,]+)?",
                stripped,
                re.I,
            )
            if subsub_match:
                self.current_subsubsection_num = subsub_match.group(1)
                title_part = subsub_match.group(2).strip() if subsub_match.group(2) else ""
                self.current_subsubsection_title = (
                    f"{self.current_subsubsection_num} {title_part}".strip()
                )
                force_new_chunk = True
                continue

            # STANDALONE NUMBERS
            if re.match(r"^#+\s*\d+\s*$", stripped):
                continue

            clean_lines.append(line)

        return self._get_current_dict("\n".join(clean_lines).strip(), force_new_chunk)

    def _reset_lower_levels(self) -> None:
        """
        Resets subsection and subsubsection state when a new section is found.
        """
        self.current_subsection_title = None
        self.current_subsection_num = None
        self.current_subsubsection_title = None
        self.current_subsubsection_num = None

    def _get_current_dict(self, clean_text: str, force_new_chunk: bool = False) -> dict[str, Any]:
        """
        Constructs a dictionary representing the current metadata state.
        """
        return {
            "section_title": self.current_section_title,
            "section_number": self.current_section_num,
            "subsection_title": self.current_subsection_title,
            "subsection_number": self.current_subsection_num,
            "subsubsection_title": self.current_subsubsection_title,
            "subsubsection_number": self.current_subsubsection_num,
            "clean_content": clean_text,
            "force_new_chunk": force_new_chunk,
        }

    def get_references(self, text: str) -> dict[str, list[str]]:
        """
        Extracts cross-references (Figure 1.1, Table 2.3, etc.) from text.
        """
        if not text:
            return {}
        lt = text.lower()
        return {
            "referenced_parts": list(set(re.findall(r"part\s+([ivxcdlm]+)", lt))),
            "referenced_figures": list(set(re.findall(r"figure\s+(\d+\.\d+)", lt))),
            "referenced_tables": list(set(re.findall(r"table\s+(\d+\.\d+)", lt))),
            "referenced_formulas": list(
                set(re.findall(r"(?:equation|formula|eq\.)\s+\(?(\d+\.\d+)\)?", lt))
            ),
            "referenced_algorithms": list(set(re.findall(r"algorithm\s+(\d+\.\d+)", lt))),
            "referenced_examples": list(set(re.findall(r"example\s+(\d+\.\d+)", lt))),
            "referenced_exercises": list(set(re.findall(r"exercise\s+(\d+\.\d+)", lt))),
            "referenced_sections": list(set(re.findall(r"section\s+(\d+\.\d+(?:\.\d+)?)", lt))),
        }
