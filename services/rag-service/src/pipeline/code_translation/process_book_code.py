from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from pipeline.code_translation.signature_stripper import strip_to_signatures
from pipeline.parsing.block_processor import BlockType

APPENDIX_START_CHAPTER = (
    28  # Chapters 1-27 are numeric, then appendices A-H map to 28-35 for sorting purposes.
)
APPENDIX_LETTERS = set("ABCDEFGH")

# Julia identifier and signature patterns.
JULIA_IDENT_PATTERN = r"[A-Za-z_\u0080-\uFFFF]\w*"
JULIA_FUNC_NAME_PATTERN = rf"{JULIA_IDENT_PATTERN}[!?]?"

# Julia definition patterns.
JULIA_ONELINER_FUNC_PATTERN = rf"^\s*({JULIA_FUNC_NAME_PATTERN})\s*\([^=\n]*\)\s*="
JULIA_BLOCK_FUNC_PATTERN = rf"^\s*function\s+({JULIA_FUNC_NAME_PATTERN})\("
JULIA_STRUCT_PATTERN = rf"^\s*(?:mutable\s+)?struct\s+({JULIA_IDENT_PATTERN})\b"

# Julia block tracking patterns.
JULIA_BLOCK_OPEN_PATTERN = (
    r"^\s*(function|(?:mutable\s+)?struct|if|for|while|begin|let|try|quote|macro|module)\b"
)
JULIA_BLOCK_END_PATTERN = r"(?<!:)\bend\b"

# Julia keywords to ignore as function names.
JULIA_STOPWORDS = frozenset(
    {"if", "for", "while", "begin", "let", "try", "catch", "finally", "end", "do"}
)

# Usage pattern templates for usage index building.
STRUCT_QUAL_PATTERN_TEMPLATE = r"::({struct_names})\b"
STRUCT_CALL_PATTERN_TEMPLATE = r"\b({struct_names})\s*\("
FUNC_CALL_PATTERN_TEMPLATE = r"\b({func_names})\s*\("
FUNC_DEF_PATTERN_TEMPLATE = r"^\s*function\s+({func_names})\s*\("
FUNC_ONELINER_DEF_PATTERN_TEMPLATE = r"^\s*({func_names})\s*\([^=\n]*\)\s*="

# Compiled Julia patterns for the entity extractor.
JULIA_ONELINER_FUNC_RE = re.compile(JULIA_ONELINER_FUNC_PATTERN)
JULIA_BLOCK_FUNC_RE = re.compile(JULIA_BLOCK_FUNC_PATTERN)
JULIA_STRUCT_RE = re.compile(JULIA_STRUCT_PATTERN)
JULIA_BLOCK_OPEN_RE = re.compile(JULIA_BLOCK_OPEN_PATTERN)
JULIA_BLOCK_END_RE = re.compile(JULIA_BLOCK_END_PATTERN)

Block = dict[str, Any]


@dataclass(frozen=True)
class UsagePatterns:
    struct_qual_pattern: re.Pattern[str] | None
    struct_call_pattern: re.Pattern[str] | None
    func_pattern: re.Pattern[str] | None
    func_def_pattern: re.Pattern[str] | None
    func_oneliner_def_pattern: re.Pattern[str] | None


class JuliaEntityExtractor:
    """Extract top-level Julia struct and function names from code."""

    def _update_block_depth(self, line: str, depth: int) -> int:
        opens = 1 if JULIA_BLOCK_OPEN_RE.match(line) else 0
        ends = len(JULIA_BLOCK_END_RE.findall(line))
        return max(0, depth + opens - ends)

    def _normalize_julia_line(self, raw: str) -> str | None:
        line = raw.split("#", 1)[0].rstrip()
        return line if line.strip() else None

    def _collect_top_level_entities(
        self,
        line: str,
        structs: list[str],
        functions: list[str],
        seen_structs: set[str],
        seen_funcs: set[str],
    ) -> None:
        m = JULIA_STRUCT_RE.match(line)
        if m:
            name = m.group(1)
            if name not in seen_structs:
                seen_structs.add(name)
                structs.append(name)

        m = JULIA_BLOCK_FUNC_RE.match(line)
        if m:
            name = m.group(1)
            if name not in JULIA_STOPWORDS and name not in seen_funcs:
                seen_funcs.add(name)
                functions.append(name)

        m = JULIA_ONELINER_FUNC_RE.match(line)
        if m:
            name = m.group(1)
            if name not in JULIA_STOPWORDS and name not in seen_funcs:
                seen_funcs.add(name)
                functions.append(name)

    def _iter_julia_lines(self, code: str) -> Iterable[str]:
        for raw in code.splitlines():
            line = self._normalize_julia_line(raw)
            if line:
                yield line

    def _extract_entities_from_lines(
        self,
        lines: Iterable[str],
    ) -> tuple[list[str], list[str]]:
        structs: list[str] = []
        functions: list[str] = []
        seen_structs: set[str] = set()
        seen_funcs: set[str] = set()
        depth = 0

        for line in lines:
            if depth == 0:
                self._collect_top_level_entities(
                    line,
                    structs,
                    functions,
                    seen_structs,
                    seen_funcs,
                )

            depth = self._update_block_depth(line, depth)

        return structs, functions

    def extract_entities(self, code: str) -> tuple[list[str], list[str]]:
        """Return top-level structs and function names defined in a Julia code block."""
        return self._extract_entities_from_lines(self._iter_julia_lines(code))


class UsageIndexBuilder:
    """Build and apply usage indices for declared entities across blocks."""

    def _collect_declared_entities(self, blocks: list[Block]) -> tuple[set[str], set[str]]:
        all_structs: set[str] = set()
        all_functions: set[str] = set()
        for block in blocks:
            all_structs.update(block.get("structs", {}).keys())
            all_functions.update(block.get("functions", {}).keys())
        return all_structs, all_functions

    def _init_usage_maps(
        self, all_structs: set[str], all_functions: set[str]
    ) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
        struct_usage: dict[str, set[str]] = {name: set() for name in all_structs}
        function_usage: dict[str, set[str]] = {name: set() for name in all_functions}
        return struct_usage, function_usage

    def _build_usage_patterns(
        self, all_structs: set[str], all_functions: set[str]
    ) -> UsagePatterns:
        struct_qual_pattern = None
        struct_call_pattern = None
        if all_structs:
            struct_names = "|".join(
                re.escape(name) for name in sorted(all_structs, key=len, reverse=True)
            )
            struct_qual_pattern = re.compile(
                STRUCT_QUAL_PATTERN_TEMPLATE.format(struct_names=struct_names)
            )
            struct_call_pattern = re.compile(
                STRUCT_CALL_PATTERN_TEMPLATE.format(struct_names=struct_names)
            )

        func_pattern = None
        func_def_pattern = None
        func_oneliner_def_pattern = None
        if all_functions:
            func_names = "|".join(
                re.escape(name) for name in sorted(all_functions, key=len, reverse=True)
            )
            func_pattern = re.compile(FUNC_CALL_PATTERN_TEMPLATE.format(func_names=func_names))
            func_def_pattern = re.compile(FUNC_DEF_PATTERN_TEMPLATE.format(func_names=func_names))
            func_oneliner_def_pattern = re.compile(
                FUNC_ONELINER_DEF_PATTERN_TEMPLATE.format(func_names=func_names)
            )

        return UsagePatterns(
            struct_qual_pattern=struct_qual_pattern,
            struct_call_pattern=struct_call_pattern,
            func_pattern=func_pattern,
            func_def_pattern=func_def_pattern,
            func_oneliner_def_pattern=func_oneliner_def_pattern,
        )

    def _record_struct_usage(
        self,
        pattern: re.Pattern[str],
        text: str,
        block_number: str,
        struct_usage: dict[str, set[str]],
    ) -> None:
        for match in pattern.finditer(text):
            name = match.group(1)
            if name:
                struct_usage[name].add(block_number)

    def _collect_defined_functions(self, text: str, patterns: UsagePatterns) -> set[str]:
        defined: set[str] = set()
        if not patterns.func_def_pattern and not patterns.func_oneliner_def_pattern:
            return defined

        for line in text.splitlines():
            def_match = patterns.func_def_pattern.match(line) if patterns.func_def_pattern else None
            if def_match:
                defined.add(def_match.group(1))
                continue
            def_match = (
                patterns.func_oneliner_def_pattern.match(line)
                if patterns.func_oneliner_def_pattern
                else None
            )
            if def_match:
                defined.add(def_match.group(1))
        return defined

    def _scan_block_usage(
        self,
        text: str,
        block_number: str,
        patterns: UsagePatterns,
        struct_usage: dict[str, set[str]],
        function_usage: dict[str, set[str]],
    ) -> None:
        if patterns.struct_qual_pattern:
            self._record_struct_usage(
                patterns.struct_qual_pattern, text, block_number, struct_usage
            )

        if patterns.struct_call_pattern:
            self._record_struct_usage(
                patterns.struct_call_pattern, text, block_number, struct_usage
            )

        if patterns.func_pattern:
            defined = self._collect_defined_functions(text, patterns)
            for match in patterns.func_pattern.finditer(text):
                name = match.group(1)
                if name not in defined:
                    function_usage[name].add(block_number)

    def _build_usage_index(
        self, blocks: list[Block]
    ) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
        all_structs, all_functions = self._collect_declared_entities(blocks)
        struct_usage, function_usage = self._init_usage_maps(all_structs, all_functions)

        if not all_structs and not all_functions:
            return struct_usage, function_usage

        patterns = self._build_usage_patterns(all_structs, all_functions)

        for block in blocks:
            text = block.get("text", "")
            block_number = block.get("number")
            if not text or not block_number:
                continue

            self._scan_block_usage(
                text,
                block_number,
                patterns,
                struct_usage,
                function_usage,
            )

        return struct_usage, function_usage

    def _extend_usage_list(
        self,
        used_list: list[str],
        usage_sorted: dict[str, list[str]],
        usage_sets: dict[str, set[str]],
        name: str,
        block_number: str,
    ) -> None:
        usage = usage_sorted.get(name)
        if not usage:
            return
        usage_set = usage_sets.get(name)
        if usage_set and block_number in usage_set:
            used_list.extend(num for num in usage if num != block_number)
        else:
            used_list.extend(usage)

    def populate_usage(self, blocks: list[Block], blocks_type: BlockType) -> None:
        struct_usage, function_usage = self._build_usage_index(blocks)

        struct_usage_sorted = {name: sorted(nums) for name, nums in struct_usage.items() if nums}
        function_usage_sorted = {
            name: sorted(nums) for name, nums in function_usage.items() if nums
        }

        for block in blocks:
            if block["block_type"] != blocks_type.value:
                continue

            block_number = block.get("number")
            if not block_number:
                continue

            for struct_name, used_list in block["structs"].items():
                self._extend_usage_list(
                    used_list,
                    struct_usage_sorted,
                    struct_usage,
                    struct_name,
                    block_number,
                )

            for function_name, used_list in block["functions"].items():
                self._extend_usage_list(
                    used_list,
                    function_usage_sorted,
                    function_usage,
                    function_name,
                    block_number,
                )


class TranslatedAlgorithmStore:
    """Load and serve translated algorithm code from JSON storage."""

    def __init__(self, translated_algos_path: Path) -> None:
        self._translated_algos_path = translated_algos_path

    def _load_translated_algorithms(self) -> list[dict[str, Any]]:
        json_path: Path = self._translated_algos_path
        with json_path.open("r", encoding="utf-8") as fh:
            return cast(list[dict[str, Any]], json.load(fh))

    def get_translated_algorithm(self, algorithm_number: str) -> str | None:
        json_data = self._load_translated_algorithms()

        for item in json_data:
            if item["algorithm_number"] == algorithm_number:
                return cast(str, item["code"])
        return None

    def get_translated_algorithms(
        self,
        algorithm_numbers: Iterable[str],
        signatures_only: bool = False,
    ) -> list[dict[str, str]]:
        translated_algorithms: list[dict[str, str]] = []
        for algorithm_number in algorithm_numbers:
            translated_algorithm = self.get_translated_algorithm(algorithm_number) or ""
            translated_algorithms.append(
                {
                    "algorithm_number": algorithm_number,
                    "translated": (
                        strip_to_signatures(translated_algorithm)
                        if signatures_only
                        else translated_algorithm
                    ),
                }
            )
        return translated_algorithms


class BookCodeProcessor:
    def __init__(
        self,
        translated_algos_path: Path,
        entity_extractor: JuliaEntityExtractor,
        usage_indexer: UsageIndexBuilder,
        algorithm_store: TranslatedAlgorithmStore,
    ) -> None:
        self._translated_algos_path = translated_algos_path
        self._entity_extractor = entity_extractor
        self._usage_indexer = usage_indexer
        self._algorithm_store = algorithm_store

    def extract_entities_from_julia_code(self, code: str) -> tuple[list[str], list[str]]:
        """Return top-level structs and function names defined in a Julia code block."""
        return self._entity_extractor.extract_entities(code)

    def _split_caption_parts(self, caption: str) -> tuple[str, str] | None:
        """Return (label, number) parts from a caption or None if unavailable."""
        parts = caption.split()
        if len(parts) < 2:
            return None
        return parts[0], parts[1]

    def extract_block_number_from_caption(self, caption: str) -> str:
        """Normalize a caption into its stable key, e.g. 'Algorithm 2.1.'"""
        parts = self._split_caption_parts(caption)
        if not parts:
            return caption
        label, number = parts
        return f"{label} {number}"

    def extract_chapter_from_block_caption(self, caption: str) -> str:
        """Extract the chapter component from a block caption string."""
        parts = self._split_caption_parts(caption)
        if not parts:
            return ""
        _, block_number = parts
        return block_number.split(".")[0]

    def _normalize_chapter(self, chapter: str | int) -> int:
        """Normalize chapter labels (including appendices) into sortable integers."""
        if isinstance(chapter, int):
            return chapter
        chapter = chapter.strip().rstrip(".")
        if chapter.isdigit():
            return int(chapter)
        if len(chapter) == 1 and chapter.upper() in APPENDIX_LETTERS:
            return APPENDIX_START_CHAPTER + (ord(chapter.upper()) - ord("A"))
        return 0

    def extract_block_chapter(self, block_number: str) -> int:
        """Extract the chapter number from a normalized block number string."""
        parts = block_number.split()
        token = parts[-1] if parts else block_number
        chapter_str = token.split(".")[0]
        return self._normalize_chapter(chapter_str)

    def get_blocks_with_chapter(self, blocks: list[Block], chapter_number: str) -> list[Block]:
        """Filter blocks to those belonging to a given chapter number."""
        chapter_blocks = []

        for block in blocks:
            if self.extract_chapter_from_block_caption(block["caption"]) == chapter_number:
                chapter_blocks.append(block)
        return chapter_blocks

    def find_related_definitions(
        self, block_number: str, blocks: list[Block]
    ) -> list[tuple[str, str]]:
        """Find (entity, block_number) pairs that reference the given block."""
        related = []
        for block in blocks:
            if block["number"] == block_number:
                continue

            for item, used_list in block["functions"].items():
                if block_number in used_list:
                    related.append((item, block["number"]))

            for item, used_list in block["structs"].items():
                if block_number in used_list:
                    related.append((item, block["number"]))
        return related

    def find_related_definitions_for_chapter(
        self,
        chapter_blocks: list[Block],
        all_blocks: list[Block],
    ) -> dict[str, list[tuple[str, str]]]:
        """Build a per-block map of related definitions for a chapter."""
        related = {}
        for block in chapter_blocks:
            block_number = block["number"]
            related[block_number] = self.find_related_definitions(block_number, all_blocks)
        return related

    def extract_block_structs_and_functions(self, blocks: list[Block]) -> None:
        """Annotate blocks with declared structs/functions and their usage lists."""
        for block in blocks:
            block["number"] = self.extract_block_number_from_caption(block["caption"])
            structs, functions = self.extract_entities_from_julia_code(block["text"])
            block["structs"] = {struct: [] for struct in structs}
            block["functions"] = {func: [] for func in functions}

    def extract_entities_usage(
        self, blocks: list[Block], blocks_type: BlockType = BlockType.ALGORITHM
    ) -> None:
        """Populate per-block usage lists for structs/functions across blocks."""
        self._usage_indexer.populate_usage(blocks, blocks_type)

    def get_translated_algorithm(self, algorithm_number: str) -> str | None:
        """Return translated code for a given algorithm number."""
        return self._algorithm_store.get_translated_algorithm(algorithm_number)

    def get_translated_algorithms(
        self,
        algorithm_numbers: Iterable[str],
        signatures_only: bool = False,
    ) -> list[dict[str, str]]:
        """Hydrate a list of algorithm numbers with translated code entries."""
        return self._algorithm_store.get_translated_algorithms(
            algorithm_numbers,
            signatures_only=signatures_only,
        )

    def filter_out_older_chapters(
        self, block_numbers: Iterable[str], current_chapter: str | int
    ) -> list[str]:
        """Filter block numbers to those from chapters before the given chapter."""
        current_chapter = self._normalize_chapter(current_chapter)
        filtered: list[str] = []
        for block_number in block_numbers:
            chapter = self.extract_block_chapter(block_number)
            if chapter < current_chapter:
                filtered.append(block_number)
        return filtered

    def format_blocks_text(self, blocks: list[Block]) -> str:
        """Render blocks as prompt-ready caption + code text."""
        return "\n".join(f"{block['caption']} \n\n {block['text']} \n\n" for block in blocks) or ""

    def format_translated_blocks(self, translated_blocks: Iterable[dict[str, str]]) -> str:
        """Render translated algorithms as prompt-ready text."""
        return (
            "\n".join(
                f"{translated['algorithm_number']} \n\n {translated['translated']} \n\n"
                for translated in translated_blocks
            )
            or ""
        )
