import argparse
import json
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol, cast

import boto3  # type: ignore[import-not-found]
from botocore.config import Config  # type: ignore[import-not-found]
from common.logging import get_logger
from pipeline.julia_code_translation.build_prompts import PromptBuilder
from pipeline.julia_code_translation.constants import TRANSLATED_ALGOS_PATH, PromptConfig
from pipeline.julia_code_translation.github_code_fetcher import GitHubCodeFetcher
from pipeline.julia_code_translation.process_book_code import (
    BookCodeProcessor,
    JuliaEntityExtractor,
    TranslatedAlgorithmStore,
    UsageIndexBuilder,
)
from pipeline.parsing.block_processor import open_block_processor

logger = get_logger(__name__)


class ModelClient(Protocol):
    def send_prompt(self, prompt: str) -> str: ...


class ResponseParser:
    """Parse model responses into structured JSON blocks."""

    def extract_json_from_text(self, text: str) -> list[dict[str, Any]]:
        start = text.find("```")
        end = text.rfind("```")

        if start == -1 or end == -1 or start == end:
            raise ValueError("JSON block not found")

        json_str = text[start + 3 : end].strip()

        if json_str.lower().startswith("json"):
            json_str = json_str[4:].lstrip()

        return cast(list[dict[str, Any]], json.loads(json_str))


class TranslationRepository:
    """Persist translation outputs as a JSON list of dicts."""

    def __init__(self, file_path: str | Path) -> None:
        self._file_path = Path(file_path)

    def _load(self) -> list[dict[str, Any]]:
        if self._file_path.exists():
            with self._file_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = []

        if not isinstance(data, list):
            raise ValueError("JSON must be a list of dicts")

        for idx, item in enumerate(data):
            if not isinstance(item, dict):
                raise ValueError(
                    f"JSON list items must be dicts; item at index {idx} is {type(item).__name__}"
                )
        return cast(list[dict[str, Any]], data)

    def append_items(self, new_items: Iterable[dict[str, Any]]) -> None:
        data = self._load()
        items_list = list(new_items)

        for idx, new_item in enumerate(items_list):
            if not isinstance(new_item, dict):
                raise TypeError(
                    f"new_items must contain dicts; "
                    f"item at index {idx} is {type(new_item).__name__}"
                )
            data.append(new_item)

        with self._file_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(
            "json_list_updated",
            path=str(self._file_path),
            added=len(items_list),
            total=len(data),
        )


class PromptStore:
    """Persist prompts to disk for inspection and replay."""

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir

    def save(self, subdir: str, filename: str, prompt: str) -> Path:
        directory = self._base_dir / subdir
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / filename
        with path.open("w", encoding="utf-8") as f:
            f.write(prompt)
        logger.info("prompt_saved", path=str(path), prompt_chars=len(prompt))
        return path


class BedrockModelClient:
    """Send prompts to Bedrock and return model responses."""

    def __init__(
        self,
        client: Any,
        model_id: str = "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
        system_prompt: str | None = None,
        max_tokens: int = 10000,
        temperature: float = 0.0,
    ) -> None:
        self._client = client
        self._model_id = model_id
        self._system_prompt = system_prompt or (
            "You are an expert at translating Julia code to idiomatic Python, "
            "maintaining consistency with existing code patterns"
        )
        self._max_tokens = max_tokens
        self._temperature = temperature

    def send_prompt(self, prompt: str) -> str:
        logger.info("sending_prompt", prompt_chars=len(prompt))
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
            "system": self._system_prompt,
            "messages": [{"role": "user", "content": prompt}],
        }

        response = self._client.invoke_model(modelId=self._model_id, body=json.dumps(body))
        response_body = json.loads(response["body"].read())
        return cast(str, response_body["content"][0]["text"])


class Translator:
    """Coordinate prompt creation, model calls, and persistence of translations."""

    def __init__(
        self,
        model_client: ModelClient,
        prompt_store: PromptStore,
        translation_repo: TranslationRepository,
        prompts_builder: PromptBuilder,
        config: PromptConfig,
        response_parser: ResponseParser,
        example_repo: TranslationRepository | None = None,
    ) -> None:
        self._model_client = model_client
        self._prompt_store = prompt_store
        self._translation_repo = translation_repo
        self._example_repo = example_repo or translation_repo
        self._prompts_builder = prompts_builder
        self._config = config
        self._response_parser = response_parser

    def _handle_response(self, response_text: str, repository: TranslationRepository) -> None:
        payload = self._response_parser.extract_json_from_text(response_text)
        repository.append_items(payload)

    def process_update_descriptions(self, julia_code: list[dict[str, Any]]) -> None:
        """Update descriptions for already-translated chapters."""
        prompts_queue: list[str] = []
        for chapter in self._config.translated_chapters:
            prompt = self._prompts_builder.build_update_descriptions_prompt(chapter, julia_code)
            self._prompt_store.save(
                "update_description", f"chapter_{chapter}_code_translation.txt", prompt
            )
            prompts_queue.append(prompt)

        logger.info("update_description_queue_built", total=len(prompts_queue))
        i = 0
        while prompts_queue:
            logger.info("processing_prompt", index=i)
            prompt = prompts_queue.pop(0)

            response_text = self._model_client.send_prompt(prompt)
            logger.info("translation_response_received", response_chars=len(response_text))
            self._handle_response(response_text, self._translation_repo)
            logger.info("prompt_processed", index=i)
            i += 1

    def process_translate_algorithms(self, julia_code: list[dict[str, Any]]) -> None:
        """Translate new algorithm chapters from Julia to Python."""
        for chapter in self._config.chapters_to_translate:
            logger.info("translating_chapter", chapter=chapter)
            prompt = self._prompts_builder.build_translate_python_code_prompt(chapter, julia_code)
            self._prompt_store.save(
                "translate_algorithms", f"chapter_{chapter}_translation.txt", prompt
            )

            response_text = self._model_client.send_prompt(prompt)

            logger.info("translation_response_received", response_chars=len(response_text))
            self._handle_response(response_text, self._translation_repo)
            logger.info("prompt_processed", chapter=chapter)

    def process_translate_examples(self, blocks: list[dict[str, Any]]) -> None:
        """Translate example blocks from Julia to Python."""
        prompts_queue: list[str] = []
        for example in self._config.example_with_code_numbers:
            prompt = self._prompts_builder.build_translate_example_prompt(example, blocks)
            self._prompt_store.save(
                "translate_examples", f"{example.replace(' ', '_')}_translation.txt", prompt
            )
            prompts_queue.append(prompt)

        logger.info("translate_examples_queue_built", total=len(prompts_queue))
        i = 0
        while prompts_queue:
            logger.info("processing_prompt", index=i)
            prompt = prompts_queue.pop(0)

            response_text = self._model_client.send_prompt(prompt)

            logger.info("translation_response_received", response_chars=len(response_text))
            self._handle_response(response_text, self._example_repo)
            logger.info("prompt_processed", index=i)
            i += 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build translation prompts from the Decision Making PDF."
    )
    parser.add_argument(
        "--pdf-path", default="dm.pdf", help="Path to the source PDF (default: dm.pdf)"
    )
    parser.add_argument(
        "--prompts-dir",
        default=PromptConfig().prompts_dir,
        help="Output directory for prompts (default: prompts)",
    )
    parser.add_argument(
        "--translated-algorithms-json",
        default=str(TRANSLATED_ALGOS_PATH),
        help="Path to translated algorithms JSON (default: translated_algorithms.json)",
    )
    return parser.parse_args()


def build_bedrock_client() -> Any:
    return boto3.client(
        service_name="bedrock-runtime",
        region_name="eu-central-1",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        config=Config(
            read_timeout=600,  # response wait time in seconds
            connect_timeout=60,  # connection timeout in seconds
        ),
    )


def build_prompt_builder(translated_algorithms_json: str, block_processor: Any) -> PromptBuilder:
    translated_algorithms_path = Path(translated_algorithms_json)
    return PromptBuilder(
        book_processor=BookCodeProcessor(
            translated_algorithms_path,
            JuliaEntityExtractor(),
            UsageIndexBuilder(),
            TranslatedAlgorithmStore(translated_algorithms_path),
        ),
        github_fetcher=GitHubCodeFetcher("https://github.com/griffinbholt/decisionmaking-code-py"),
        block_processor=block_processor,
    )


def build_translator(
    prompts_dir: Path,
    translated_algorithms_json: str,
    prompts_builder: PromptBuilder,
    config: PromptConfig,
    model_client: ModelClient,
) -> Translator:
    prompt_store = PromptStore(prompts_dir)
    translation_repo = TranslationRepository(translated_algorithms_json)
    example_repo = TranslationRepository("translated_examples.json")

    return Translator(
        model_client=model_client,
        prompt_store=prompt_store,
        translation_repo=translation_repo,
        prompts_builder=prompts_builder,
        config=config,
        response_parser=ResponseParser(),
        example_repo=example_repo,
    )


def main() -> None:
    args = parse_args()

    client = build_bedrock_client()
    prompts_dir = Path(args.prompts_dir)
    config = PromptConfig()

    with open_block_processor(args.pdf_path) as block_processor:
        blocks = block_processor.extract_algorithms_and_examples()
        julia_code = block_processor.extract_algorithms(blocks)

        prompts_builder = build_prompt_builder(args.translated_algorithms_json, block_processor)
        model_client = BedrockModelClient(client)

        translator = build_translator(
            prompts_dir=prompts_dir,
            translated_algorithms_json=args.translated_algorithms_json,
            prompts_builder=prompts_builder,
            config=config,
            model_client=model_client,
        )
        logger.info("translation_started", prompts_dir=str(prompts_dir))
        translator.process_update_descriptions(julia_code)
        translator.process_translate_algorithms(julia_code)
        translator.process_translate_examples(blocks)
        logger.info("translation_completed")


if __name__ == "__main__":
    main()
