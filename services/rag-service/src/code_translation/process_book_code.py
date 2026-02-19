import json
import re
from pathlib import Path
from typing import Iterable, Optional

from code_translation.build_prompts import TRANSLATED_ALGOS_PATH
from code_translation.signature_stripper import strip_to_signatures
from pdf_parsing.extract_algorithms_and_examples import BlockType

APPENDIX_START_CHAPTER = 28
APPENDIX_LETTERS = set("ABCDEFGH")


class BookCodeProcessor:
    def __init__(self, translated_algos_path: Path = TRANSLATED_ALGOS_PATH) -> None:
        self._translated_algos_path = translated_algos_path

    def extract_entities_from_julia_code(self, code: str):
        """Return top-level structs and function names defined in a Julia code block."""
        ident = r"[A-Za-z_\u0080-\uFFFF]\w*"
        func_name = rf"{ident}[!?]?"

        oneliner_func_re = re.compile(rf"^\s*({func_name})\s*\([^=\n]*\)\s*=")
        block_func_re = re.compile(rf"^\s*function\s+({func_name})\(")
        struct_re = re.compile(rf"^\s*(?:mutable\s+)?struct\s+({ident})\b")

        block_open_re = re.compile(
            r"^\s*(function|(?:mutable\s+)?struct|if|for|while|begin|let|try|quote|macro|module)\b"
        )

        block_end_re = re.compile(r"(?<!:)\bend\b")

        stopwords = {
            "if", "for", "while", "begin", "let",
            "try", "catch", "finally", "end", "do"
        }

        structs, functions = [], []
        seen_structs, seen_funcs = set(), set()

        depth = 0

        for raw in code.splitlines():
            line = raw.split("#", 1)[0].rstrip()
            if not line.strip():
                continue

            opens = 1 if block_open_re.match(line) else 0

            ends = len(block_end_re.findall(line))

            # Only capture top-level declarations to avoid nested helpers.
            if depth == 0:
                m = struct_re.match(line)
                if m:
                    name = m.group(1)
                    if name not in seen_structs:
                        seen_structs.add(name)
                        structs.append(name)

                m = block_func_re.match(line)
                if m:
                    name = m.group(1)
                    if name not in stopwords and name not in seen_funcs:
                        seen_funcs.add(name)
                        functions.append(name)

                m = oneliner_func_re.match(line)
                if m:
                    name = m.group(1)
                    if name not in stopwords and name not in seen_funcs:
                        seen_funcs.add(name)
                        functions.append(name)

            depth = max(0, depth + opens - ends)

        return structs, functions

    def extract_block_number_from_caption(self, caption: str) -> str:
        """Normalize a caption into its stable key, e.g. 'Algorithm 2.1.'"""
        parts = caption.split()
        if len(parts) < 2:
            return caption
        return f"{parts[0]} {parts[1]}"

    def extract_chapter_from_block_caption(self, caption: str) -> str:
        """Extract the chapter component from a block caption string."""
        parts = caption.split()
        if len(parts) < 2:
            return ""
        block_number = parts[1]
        return block_number.split(".")[0]

    def get_blocks_with_chapter(self, blocks, chapter_number: str):
        """Filter blocks to those belonging to a given chapter number."""
        chapter_blocks = []

        for block in blocks:
            if self.extract_chapter_from_block_caption(block["caption"]) == chapter_number:
                chapter_blocks.append(block)
        return chapter_blocks

    def find_related_definitions(self, block_number, blocks):
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

    def find_related_definitions_for_chapter(self, chapter_blocks, all_blocks):
        """Build a per-block map of related definitions for a chapter."""
        related = {}
        for block in chapter_blocks:
            block_number = block["number"]
            related[block_number] = self.find_related_definitions(block_number, all_blocks)
        return related

    def extract_block_structs_and_functions(self, blocks) -> None:
        """Annotate blocks with declared structs/functions and their usage lists."""
        for block in blocks:
            block["number"] = self.extract_block_number_from_caption(block["caption"])
            structs, functions = self.extract_entities_from_julia_code(block["text"])
            block["structs"] = {struct: [] for struct in structs}
            block["functions"] = {func: [] for func in functions}

    def _build_usage_index(self, blocks) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
        """Build inverted indices of struct and function usage across blocks.

        The index maps each entity name to block numbers where it is used (not defined).
        """
        all_structs = set()
        all_functions = set()
        for block in blocks:
            all_structs.update(block.get("structs", {}).keys())
            all_functions.update(block.get("functions", {}).keys())

        struct_usage: dict[str, set[str]] = {name: set() for name in all_structs}
        function_usage: dict[str, set[str]] = {name: set() for name in all_functions}

        if not all_structs and not all_functions:
            return struct_usage, function_usage

        # Single-pass regex matches keep scanning per block fast even with many entities.
        struct_pattern = None
        if all_structs:
            struct_names = "|".join(re.escape(name) for name in sorted(all_structs, key=len, reverse=True))
            struct_pattern = re.compile(rf"(?:(?:::)({struct_names})\b)|(?:\b({struct_names})\s*\()")

        func_pattern = None
        if all_functions:
            func_names = "|".join(re.escape(name) for name in sorted(all_functions, key=len, reverse=True))
            func_pattern = re.compile(rf"\b({func_names})\s*\(")
            func_def_pattern = re.compile(rf"^\s*function\s+({func_names})\s*\(")
            func_oneliner_def_pattern = re.compile(rf"^\s*({func_names})\s*\([^=\n]*\)\s*=")

        for block in blocks:
            text = block.get("text", "")
            block_number = block.get("number")
            if not text or not block_number:
                continue

            if struct_pattern:
                for match in struct_pattern.finditer(text):
                    name = match.group(1) or match.group(2)
                    if name:
                        struct_usage[name].add(block_number)

            if func_pattern:
                defined = set()
                for line in text.splitlines():
                    def_match = func_def_pattern.match(line) if func_def_pattern else None
                    if def_match:
                        defined.add(def_match.group(1))
                        continue
                    def_match = func_oneliner_def_pattern.match(line) if func_oneliner_def_pattern else None
                    if def_match:
                        defined.add(def_match.group(1))

                for match in func_pattern.finditer(text):
                    name = match.group(1)
                    if name not in defined:
                        function_usage[name].add(block_number)

        return struct_usage, function_usage

    def extract_entities_usage(self, blocks, blocks_type: BlockType = BlockType.ALGORITHM) -> None:
        """Populate per-block usage lists for structs/functions across blocks."""
        struct_usage, function_usage = self._build_usage_index(blocks)

        # Pre-sort usage lists once to avoid per-block sorting.
        struct_usage_sorted = {name: sorted(nums) for name, nums in struct_usage.items() if nums}
        function_usage_sorted = {name: sorted(nums) for name, nums in function_usage.items() if nums}

        for block in blocks:
            if block["block_type"] != blocks_type.value:
                continue

            block_number = block.get("number")
            if not block_number:
                continue

            for struct_name, used_list in block["structs"].items():
                usage = struct_usage_sorted.get(struct_name)
                if not usage:
                    continue
                if block_number in struct_usage.get(struct_name, set()):
                    used_list.extend(num for num in usage if num != block_number)
                else:
                    used_list.extend(usage)

            for function_name, used_list in block["functions"].items():
                usage = function_usage_sorted.get(function_name)
                if not usage:
                    continue
                if block_number in function_usage.get(function_name, set()):
                    used_list.extend(num for num in usage if num != block_number)
                else:
                    used_list.extend(usage)

    def _load_translated_algorithms(self) -> list:
        """Load translated algorithms JSON once per run."""
        json_path: Path = self._translated_algos_path
        with json_path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def get_translated_algorithm(self, algorithm_number: str) -> Optional[str]:
        """Return translated code for a given algorithm number."""
        json_data = self._load_translated_algorithms()

        for item in json_data:
            if item["algorithm_number"] == algorithm_number:
                return item["code"]
        return None

    def _normalize_chapter(self, chapter) -> int:
        """Convert a chapter identifier to a numeric value (A-H mapped after 28)."""
        chapter_str = str(chapter)
        if chapter_str in APPENDIX_LETTERS:
            return APPENDIX_START_CHAPTER + ord(chapter_str) - ord("A")
        return int(chapter_str)

    def extract_block_chapter(self, block_number: str) -> int:
        """Extract and normalize chapter number from a block key."""
        number = block_number.split(" ")[1]
        chapter = number.split(".")[0]
        return self._normalize_chapter(chapter)

    def get_translated_algorithms(self, algorithm_numbers: Iterable[str], signatures_only: bool = False) -> list[dict[str, str]]:
        """Hydrate a list of algorithm numbers with translated code entries."""
        translated_algorithms = []
        for algorithm_number in algorithm_numbers:
            translated_algorithm = self.get_translated_algorithm(algorithm_number)
            translated_algorithms.append([
                {
                    "algorithm_number": algorithm_number,
                    "translated": strip_to_signatures(translated_algorithm) if signatures_only else translated_algorithm,
                }
            ])
        return translated_algorithms

    def filter_out_older_chapters(self, block_numbers, current_chapter):
        """Filter block numbers to those at or before the given chapter."""
        current_chapter = self._normalize_chapter(current_chapter)
        filtered = []
        for block_number in block_numbers:
            chapter = self.extract_block_chapter(block_number)
            if chapter < current_chapter:
                filtered.append(block_number)
        return filtered

    def format_blocks_text(self, blocks) -> str:
        """Render blocks as prompt-ready caption + code text."""
        return "\n".join(f"{block['caption']} \n\n {block['text']} \n\n" for block in blocks) or ""

    def format_translated_blocks(self, translated_blocks) -> str:
        """Render translated algorithms as prompt-ready text."""
        return "\n".join(
            f"{translated['algorithm_number']} \n\n {translated['translated']} \n\n"
            for translated in translated_blocks
        ) or ""
