import os

import boto3
import json
from pathlib import Path
import argparse
from typing import Any, Iterable

from botocore.config import Config

from code_translation.build_prompts import TRANSLATED_CHAPTERS, CHAPTERS_TO_TRANSLATE, \
    EXAMPLE_WITH_CODE_NUMBERS, PromptBuilder, TRANSLATED_ALGOS_PATH
from code_translation.process_book_code import BookCodeProcessor
from packages.common.src.common.logging import get_logger
from pdf_parsing.extract_algorithms_and_examples import extract_algorithms_and_examples, extract_algorithms

logger = get_logger(__name__)


class Translator:
    """Coordinates prompt creation, model calls, and persistence of translations."""

    def __init__(
        self,
        client: Any,
        prompts_dir: Path,
        translated_algorithms_json: str | Path,
        prompts_builder: PromptBuilder,
    ) -> None:
        self._client = client
        self._prompts_dir = prompts_dir
        self._translated_algorithms_json = translated_algorithms_json
        self._prompts_builder = prompts_builder

    @staticmethod
    def extract_json_from_text(text: str) -> list[dict[str, Any]]:
        """
        Extract JSON between the first ``` and the last ```.
        Raises ValueError if JSON is missing or invalid.
        """
        start = text.find("```")
        end = text.rfind("```")

        if start == -1 or end == -1 or start == end:
            raise ValueError("JSON block not found")

        json_str = text[start + 3:end].strip()

        # Remove optional 'json' tag after ```
        if json_str.lower().startswith("json"):
            json_str = json_str[4:].lstrip()

        return json.loads(json_str)

    @staticmethod
    def add_dict_to_json_list(file_path: str | Path, new_items: Iterable[dict[str, Any]]) -> None:
        """
        Load a JSON list of dicts, append new dicts,
        and write the file back.
        """
        file_path = Path(file_path)
        items_list = list(new_items)
        # 1. Read the file
        if file_path.exists():
            with file_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = []
        # 2. Validate list type
        if not isinstance(data, list):
            raise ValueError("JSON must be a list of dicts")
        # 3. Append new dicts
        for new_item in items_list:
            data.append(new_item)
        # 4. Write back
        with file_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("json_list_updated", path=str(file_path), added=len(items_list), total=len(data))

    def send_prompt(self, prompt: str) -> str:
        """Send a prompt to Bedrock and return the model text response."""
        logger.info("sending_prompt", prompt_chars=len(prompt))
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 10000,
            "temperature": 0.0,
            "system": "You are an expert at translating Julia code to idiomatic Python, maintaining consistency with existing code patterns",
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }

        response = self._client.invoke_model(
            modelId="eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
            body=json.dumps(body)
        )

        response_body = json.loads(response["body"].read())

        return response_body["content"][0]["text"]

    def _persist_prompt(self, directory: Path, filename: str, prompt: str) -> None:
        """Persist a prompt to disk for inspection/replay."""
        directory.mkdir(parents=True, exist_ok=True)
        with open(directory / filename, "w", encoding="utf-8") as f:
            f.write(prompt)
        logger.info("prompt_saved", path=str(directory / filename), prompt_chars=len(prompt))

    def process_update_descriptions(self, julia_code: list[dict[str, Any]]) -> None:
        """Update descriptions for already-translated chapters."""
        prompts_queue: list[str] = []
        for chapter in TRANSLATED_CHAPTERS:
            prompt = self._prompts_builder.build_update_descriptions_prompt(chapter, julia_code)
            update_description_dir = self._prompts_dir / "update_description"
            self._persist_prompt(update_description_dir, f"chapter_{chapter}_code_translation.txt", prompt)
            prompts_queue.append(prompt)

        logger.info("update_description_queue_built", total=len(prompts_queue))
        i = 0
        while prompts_queue:
            logger.info("processing_prompt", index=i)
            prompt = prompts_queue.pop(0)

            response_text = self.send_prompt(prompt)
            logger.info("translation_response_received", response_chars=len(response_text))
            self.add_dict_to_json_list(self._translated_algorithms_json, self.extract_json_from_text(response_text))
            logger.info("prompt_processed", index=i)
            i += 1

    def process_translate_algorithms(self, julia_code: list[dict[str, Any]]) -> None:
        """Translate new algorithm chapters from Julia to Python."""
        for chapter in CHAPTERS_TO_TRANSLATE:
            logger.info("translating_chapter", chapter=chapter)
            prompt = self._prompts_builder.build_translate_python_code_prompt(chapter, julia_code)
            translate_algorithms_dir = self._prompts_dir / "translate_algorithms"
            self._persist_prompt(translate_algorithms_dir, f"chapter_{chapter}_translation.txt", prompt)

            response_text = self.send_prompt(prompt)

            logger.info("translation_response_received", response_chars=len(response_text))
            self.add_dict_to_json_list(self._translated_algorithms_json, self.extract_json_from_text(response_text))
            logger.info("prompt_processed", chapter=chapter)

    def process_translate_examples(self, blocks: list[dict[str, Any]]) -> None:
        """Translate example blocks from Julia to Python."""
        prompts_queue: list[str] = []
        for example in EXAMPLE_WITH_CODE_NUMBERS:
            prompt = self._prompts_builder.build_translate_example_prompt(example, blocks)
            translate_examples_dir = self._prompts_dir / "translate_examples"
            self._persist_prompt(translate_examples_dir, f"{example.replace(' ', '_')}_translation.txt", prompt)
            prompts_queue.append(prompt)

        logger.info("translate_examples_queue_built", total=len(prompts_queue))
        i = 0
        while prompts_queue:
            logger.info("processing_prompt", index=i)
            prompt = prompts_queue.pop(0)

            response_text = self.send_prompt(prompt)

            logger.info("translation_response_received", response_chars=len(response_text))
            self.add_dict_to_json_list("translated_examples.json", self.extract_json_from_text(response_text))
            logger.info("prompt_processed", index=i)
            i += 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Build translation prompts from the Decision Making PDF.")
    parser.add_argument("--pdf-path", default="dm.pdf", help="Path to the source PDF (default: dm.pdf)")
    parser.add_argument("--prompts-dir", default="prompts", help="Output directory for prompts (default: prompts)")
    parser.add_argument(
        "--translated-algorithms-json",
        default="translated_algorithms.json",
        help="Path to translated algorithms JSON (default: translated_algorithms.json)",
    )
    args = parser.parse_args()

    client = boto3.client(
        service_name="bedrock-runtime",
        region_name="eu-central-1",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        config=Config(
            read_timeout=600,      # response wait time in seconds
            connect_timeout=60,    # connection timeout in seconds
        ),
    )

    prompts_dir = Path(args.prompts_dir)

    blocks = extract_algorithms_and_examples(args.pdf_path)
    julia_code = extract_algorithms(blocks)

    prompts_builder = PromptBuilder(book_processor=BookCodeProcessor(TRANSLATED_ALGOS_PATH))

    translator = Translator(
        client=client,
        prompts_dir=prompts_dir,
        translated_algorithms_json=args.translated_algorithms_json,
        prompts_builder=prompts_builder
    )
    logger.info("translation_started", prompts_dir=str(prompts_dir))
    translator.process_update_descriptions(julia_code)
    translator.process_translate_algorithms(julia_code)
    translator.process_translate_examples(blocks)
    logger.info("translation_completed")


if __name__ == "__main__":
    main()
