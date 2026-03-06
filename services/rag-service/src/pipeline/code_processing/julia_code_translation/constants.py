from dataclasses import dataclass, field
from pathlib import Path

TRANSLATED_ALGOS_PATH = Path("translated_algorithms.json")


@dataclass(frozen=True)
class PromptConfig:
    """Centralized configuration for prompt-building constants."""

    prompts_dir: str = "prompts"
    example_with_code_numbers: list[str] = field(
        default_factory=lambda: [
            "Example 2.3.",
            "Example 2.5.",
            "Example 4.1.",
            "Example 4.2.",
            "Example 9.10.",
            "Example 10.1.",
            "Example 11.2.",
            "Example 15.2.",
            "Example 17.2.",
            "Example 17.3.",
            "Example 17.4.",
            "Example 21.1.",
            "Example 22.1.",
            "Example 22.3.",
            "Example 22.6.",
        ]
    )
    translated_chapters: list[str] = field(
        default_factory=lambda: [
            "02",
            "03",
            "04",
            "05",
            "06",
            "07",
            "08",
            "09",
            "10",
            "11",
            "12",
            "14",
            "15",
            "16",
            "17",
            "20",
            "24",
        ]
    )
    chapters_to_translate: list[str] = field(
        default_factory=lambda: ["13", "18", "19", "21", "22", "23", "25", "26", "27", "E"]
    )
