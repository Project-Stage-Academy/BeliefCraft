import re
from typing import Any


class MetadataExtractor:
    """
    Class for tracking and extracting hierarchical document metadata and references.
    Maintains state of current section, subsection, and subsubsection levels.
    """

    def __init__(self) -> None:
        self.current_part: str | None = None
        self.current_part_title: str | None = None
        self.current_section_title: str | None = None
        self.current_section_num: str | None = None
        self.current_subsection_title: str | None = None
        self.current_subsection_num: str | None = None
        self.current_subsubsection_title: str | None = None
        self.current_subsubsection_num: str | None = None

    def set_part(self, part: str, part_title: str) -> None:
        """Set current part metadata and reset lower hierarchy levels."""
        self.current_part = part
        self.current_part_title = part_title.strip()
        self.current_section_title = None
        self.current_section_num = None
        self._reset_lower_levels()

    def get_meta(self) -> dict[str, Any]:
        """Get current metadata state without content."""
        return self._get_current_dict("")

    def process_content_and_get_meta(
        self, content: str, update_meta: bool = True
    ) -> dict[str, Any]:
        """
        Analyzes raw text to detect headers and update the current hierarchy state.
        Filters out metadata-only lines (like page numbers) from the clean content.

        Args:
            content (str): Raw text block from a document page.

        Returns:
            dict: Current metadata state including cleaned text and a 'force_new_chunk' flag.
        """
        lines = content.split("\n")
        clean_lines: list[str] = []
        force_new_chunk = False

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            header_match = re.match(
                r"^#+\s*([\dA-Z]+(?:\.[\dA-Z]+){0,2})\.?(?:\s+(.*))?$", stripped
            )
            if header_match:
                if not update_meta:
                    continue
                number = header_match.group(1)
                title = (header_match.group(2) or "").strip()
                depth = number.count(".")

                if depth == 0:
                    self.current_section_num = number
                    self.current_section_title = title.strip()
                    self._reset_lower_levels()
                elif depth == 1:
                    self.current_subsection_num = number
                    self.current_subsection_title = title.strip()
                    self.current_subsubsection_title = None
                    self.current_subsubsection_num = None
                elif depth == 2:
                    self.current_subsubsection_num = number
                    self.current_subsubsection_title = title.strip()

                force_new_chunk = True
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
            "part": self.current_part,
            "part_title": self.current_part_title,
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
        lt = text.lower().replace("$", "")
        result = {
            "referenced_parts": list(set(re.findall(r"part\s+([ivxcdlm]+)\b", lt))),
            "referenced_figures": list(set(re.findall(r"figure\s+([a-z\d]+\.\d+)", lt))),
            "referenced_tables": list(set(re.findall(r"table\s+([a-z\d]+\.\d+)", lt))),
            "referenced_formulas": list(
                set(re.findall(r"(?:equation|formula|eq\.)\s+\(?([a-z\d]+\.\d+)\)?", lt))
            ),
            "referenced_algorithms": list(set(re.findall(r"algorithm\s+([a-z\d]+\.\d+)", lt))),
            "referenced_examples": list(set(re.findall(r"example\s+([a-z\d]+\.\d+)", lt))),
            "referenced_exercises": list(set(re.findall(r"exercise\s+([a-z\d]+\.\d+)", lt))),
            "referenced_sections": list(
                set(re.findall(r"section\s+([a-z\d]+\.\d+(?:\.\d+)?)", lt))
            ),
        }
        for key, value in result.items():
            result[key] = [v.upper() for v in value]
        return result
