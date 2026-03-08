"""
Skill management tools for dynamic domain expertise loading.

This module provides tools that allow the ReAct agent to discover and load
domain-specific diagnostic skills on demand using the Progressive Disclosure pattern:

- Tier 1: Discovery (system prompt shows skill catalog)
- Tier 2: Activation (load_skill returns full SKILL.md body)
- Tier 3: Deep dive (read_skill_file returns supporting docs)

These tools operate on local file system (no HTTP), unlike environment tools.
"""

import time
from typing import Any

from app.core.constants import CACHE_TTL_RAG_TOOLS
from app.services.skill_store import SkillStore
from app.tools.base import BaseTool, ToolMetadata
from common.logging import get_logger

logger = get_logger(__name__)


class LoadSkillTool(BaseTool):
    """
    Load expert knowledge for a specific skill.

    Returns the full SKILL.md instructions plus a list of available
    supporting files for deeper investigation.

    This tool operates synchronously on local file system, wrapped in async
    for compatibility with the agent's async tool execution pipeline.
    """

    def __init__(self, store: SkillStore) -> None:
        """
        Initialize tool with a SkillStore instance.

        Args:
            store: SkillStore configured with skills directory
        """
        self.store = store
        super().__init__()

    def get_metadata(self) -> ToolMetadata:
        """Generate metadata with dynamic skill list in description."""
        # Build list of available skills for LLM
        skill_names = self.store.get_skill_names()
        available = ", ".join(skill_names) if skill_names else "none"

        return ToolMetadata(
            name="load_skill",
            description=(
                f"Load expert diagnostic workflow for a domain-specific task. "
                f"Returns JSON with full instructions and list of supporting files.\n\n"
                f"Available skills: {available}\n\n"
                f"Use this when the user's query matches a skill's domain "
                f"(e.g., inventory discrepancies, procurement risk, capacity issues)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": (
                            f"Exact name of the skill to load. " f"Must be one of: {available}"
                        ),
                    },
                },
                "required": ["skill_name"],
            },
            category="skill",
            cache_ttl=CACHE_TTL_RAG_TOOLS,  # 24 hours - skills are static knowledge
            skip_cache=False,
        )

    async def execute(self, skill_name: str, **kwargs: Any) -> dict[str, Any]:  # type: ignore[override]
        """
        Load a skill by name.

        Args:
            skill_name: Name of the skill (directory name)
            **kwargs: Additional parameters (ignored)

        Returns:
            Dict with skill_name, description, instructions, and available_files.
            On error, returns dict with 'error' key and list of available skills.
        """
        start = time.perf_counter()

        logger.info(
            "load_skill_requested",
            tier=2,
            skill=skill_name,
        )

        # Sync operation (SkillStore is sync)
        parsed = self.store.load(skill_name)

        if parsed is None:
            # Skill not found - return error with valid options
            valid_skills = self.store.get_skill_names()
            duration_ms = int((time.perf_counter() - start) * 1000)

            logger.warning(
                "load_skill_not_found",
                tier=2,
                skill=skill_name,
                duration_ms=duration_ms,
                available_count=len(valid_skills),
            )

            return {
                "error": f"Skill '{skill_name}' not found",
                "available_skills": valid_skills,
                "message": (
                    f"The skill '{skill_name}' does not exist. "
                    f"Please choose from the available skills list."
                ),
            }

        # Success - return skill content
        available_files = self.store.list_supporting_files(skill_name)
        duration_ms = int((time.perf_counter() - start) * 1000)

        logger.info(
            "load_skill_success",
            tier=2,
            skill=skill_name,
            duration_ms=duration_ms,
            content_length=len(parsed.content),
            supporting_files_count=len(available_files),
        )

        return {
            "skill_name": skill_name,
            "description": parsed.metadata.description,
            "version": parsed.metadata.version,
            "tags": list(parsed.metadata.tags),
            "instructions": parsed.content,
            "available_files": available_files,
        }


class ReadSkillFileTool(BaseTool):
    """
    Read a supporting file from a skill directory.

    Use this for deep-dive reference material like checklists, algorithms,
    or data schemas referenced in the main SKILL.md instructions.

    Security: Validates filenames to prevent directory traversal attacks.
    """

    def __init__(self, store: SkillStore) -> None:
        """
        Initialize tool with a SkillStore instance.

        Args:
            store: SkillStore configured with skills directory
        """
        self.store = store
        super().__init__()

    def get_metadata(self) -> ToolMetadata:
        """Generate metadata with dynamic skill list in description."""
        skill_names = self.store.get_skill_names()
        available = ", ".join(skill_names) if skill_names else "none"

        return ToolMetadata(
            name="read_skill_file",
            description=(
                f"Read a supporting file from a skill's directory. "
                f"Use this to access detailed reference documents listed in "
                f"the 'available_files' field of a loaded skill.\n\n"
                f"Available skills: {available}\n\n"
                f"Example: After loading 'inventory-discrepancy-audit', "
                f"you can read 'SENSOR_CALIBRATION_CHECKLIST.md' for detailed procedures."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": (
                            f"Name of the skill that owns the file. " f"Must be one of: {available}"
                        ),
                    },
                    "filename": {
                        "type": "string",
                        "description": (
                            "Relative filename from the skill's 'available_files' list. "
                            "Example: 'ALGORITHMS.md' or 'examples/scenario1.md'"
                        ),
                    },
                },
                "required": ["skill_name", "filename"],
            },
            category="skill",
            cache_ttl=CACHE_TTL_RAG_TOOLS,  # 24 hours
            skip_cache=False,
        )

    async def execute(  # type: ignore[override]
        self, skill_name: str, filename: str, **kwargs: Any
    ) -> dict[str, Any]:
        """
        Read a supporting file from a skill directory.

        Args:
            skill_name: Name of the skill (directory name)
            filename: Relative path to file within skill directory
            **kwargs: Additional parameters (ignored)

        Returns:
            Dict with skill_name, filename, and content.
            On error, returns dict with 'error' key.
        """
        start = time.perf_counter()

        logger.info(
            "read_skill_file_requested",
            tier=3,
            skill=skill_name,
            file=filename,
        )

        try:
            # Sync operation (SkillStore is sync)
            content = self.store.read_supporting_file(skill_name, filename)
            duration_ms = int((time.perf_counter() - start) * 1000)

            logger.info(
                "read_skill_file_success",
                tier=3,
                skill=skill_name,
                file=filename,
                duration_ms=duration_ms,
                content_length=len(content),
            )

            return {
                "skill_name": skill_name,
                "filename": filename,
                "content": content,
            }

        except FileNotFoundError as e:
            duration_ms = int((time.perf_counter() - start) * 1000)

            logger.warning(
                "read_skill_file_not_found",
                tier=3,
                skill=skill_name,
                file=filename,
                duration_ms=duration_ms,
                error=str(e),
            )

            # List available files to help LLM self-correct
            available_files = self.store.list_supporting_files(skill_name)

            return {
                "error": f"File not found: {skill_name}/{filename}",
                "available_files": available_files,
                "message": (
                    f"The file '{filename}' does not exist in skill '{skill_name}'. "
                    f"Available files: {', '.join(available_files) if available_files else 'none'}"
                ),
            }

        except ValueError as e:
            duration_ms = int((time.perf_counter() - start) * 1000)

            logger.error(
                "read_skill_file_invalid",
                tier=3,
                skill=skill_name,
                file=filename,
                duration_ms=duration_ms,
                error=str(e),
            )

            return {
                "error": f"Invalid file path: {str(e)}",
                "message": (
                    f"The filename '{filename}' is invalid (security check failed). "
                    f"Use relative paths only, without '..' or absolute paths."
                ),
            }

        except Exception as e:
            duration_ms = int((time.perf_counter() - start) * 1000)

            logger.error(
                "read_skill_file_error",
                tier=3,
                skill=skill_name,
                file=filename,
                duration_ms=duration_ms,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )

            return {
                "error": f"Error reading file: {str(e)}",
                "message": f"Unexpected error while reading '{filename}' from '{skill_name}'.",
            }


class ReadSkillFilesTool(BaseTool):
    """
    Read multiple supporting files from a skill directory in one call.

    Use this to efficiently retrieve several reference documents at once,
    reducing ReAct loop iterations. Returns partial results if some files fail.

    Max 3 files per call to prevent excessive token usage.
    """

    MAX_FILES_PER_BATCH = 3

    def __init__(self, store: SkillStore) -> None:
        """
        Initialize tool with a SkillStore instance.

        Args:
            store: SkillStore configured with skills directory
        """
        self.store = store
        super().__init__()

    def get_metadata(self) -> ToolMetadata:
        """Generate metadata with dynamic skill list in description."""
        skill_names = self.store.get_skill_names()
        available = ", ".join(skill_names) if skill_names else "none"

        return ToolMetadata(
            name="read_skill_files",
            description=(
                f"Read multiple supporting files from a skill's directory in one call. "
                f"More efficient than calling read_skill_file multiple times. "
                f"Returns partial results if some files are not found.\n\n"
                f"Available skills: {available}\n\n"
                f"Max {self.MAX_FILES_PER_BATCH} files per batch. "
                f"Example: Read ['GUIDE.md', 'CHECKLIST.md', 'formulas.txt'] at once."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": (
                            f"Name of the skill that owns the files. "
                            f"Must be one of: {available}"
                        ),
                    },
                    "filenames": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            f"List of relative filenames to read (max {self.MAX_FILES_PER_BATCH}). "
                            f"Example: ['ALGORITHMS.md', 'examples/scenario1.md']"
                        ),
                        "minItems": 1,
                        "maxItems": self.MAX_FILES_PER_BATCH,
                    },
                },
                "required": ["skill_name", "filenames"],
            },
            category="skill",
            cache_ttl=CACHE_TTL_RAG_TOOLS,  # 24 hours
            skip_cache=False,
        )

    async def execute(  # type: ignore[override]
        self, skill_name: str, filenames: list[str], **kwargs: Any
    ) -> dict[str, Any]:
        """
        Read multiple supporting files from a skill directory.

        Args:
            skill_name: Name of the skill (directory name)
            filenames: List of relative paths to files (max 3)
            **kwargs: Additional parameters (ignored)

        Returns:
            Dict with skill_name, success (dict of filename->content),
            and errors (dict of filename->error_message).
        """
        start = time.perf_counter()

        logger.info(
            "read_skill_files_batch_requested",
            tier=3,
            skill=skill_name,
            files_count=len(filenames),
            files=filenames,
        )

        # Validate batch size
        if len(filenames) > self.MAX_FILES_PER_BATCH:
            return {
                "error": f"Too many files requested: {len(filenames)}",
                "message": (
                    f"Maximum {self.MAX_FILES_PER_BATCH} files per batch. "
                    f"You requested {len(filenames)} files. "
                    f"Split into multiple calls or use read_skill_file for single files."
                ),
                "max_batch_size": self.MAX_FILES_PER_BATCH,
            }

        if not filenames:
            return {
                "error": "Empty filenames list",
                "message": "Provide at least one filename to read.",
            }

        # Read all files, collecting successes and errors
        success: dict[str, str] = {}
        errors: dict[str, str] = {}

        for filename in filenames:
            try:
                content = self.store.read_supporting_file(skill_name, filename)
                success[filename] = content
                logger.debug(
                    "read_skill_file_batch_item_success",
                    tier=3,
                    skill=skill_name,
                    file=filename,
                    content_length=len(content),
                )

            except FileNotFoundError as e:
                errors[filename] = f"File not found: {str(e)}"
                logger.debug(
                    "read_skill_file_batch_item_not_found",
                    tier=3,
                    skill=skill_name,
                    file=filename,
                )

            except ValueError as e:
                errors[filename] = f"Invalid path (security check failed): {str(e)}"
                logger.debug(
                    "read_skill_file_batch_item_invalid",
                    tier=3,
                    skill=skill_name,
                    file=filename,
                )

            except Exception as e:
                errors[filename] = f"Unexpected error: {str(e)}"
                logger.warning(
                    "read_skill_file_batch_item_error",
                    tier=3,
                    skill=skill_name,
                    file=filename,
                    error=str(e),
                    error_type=type(e).__name__,
                )

        duration_ms = int((time.perf_counter() - start) * 1000)

        logger.info(
            "read_skill_files_batch_complete",
            tier=3,
            skill=skill_name,
            files_requested=len(filenames),
            files_success=len(success),
            files_failed=len(errors),
            duration_ms=duration_ms,
        )

        # Build result with statistics
        result: dict[str, Any] = {
            "skill_name": skill_name,
            "files_requested": len(filenames),
            "files_success": len(success),
            "files_failed": len(errors),
        }

        if success:
            result["success"] = success

        if errors:
            result["errors"] = errors
            # Add available files hint if any files failed
            try:
                available_files = self.store.list_supporting_files(skill_name)
                result["available_files"] = available_files
            except Exception as e:
                logger.debug(
                    "read_skill_files_batch_list_files_failed",
                    skill=skill_name,
                    error=str(e),
                )

        return result
