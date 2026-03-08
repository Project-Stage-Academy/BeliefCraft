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

from app.core.constants import CACHE_TTL_SKILLS
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
                "Load expert diagnostic workflow for a domain-specific task. "
                "Returns JSON with full instructions and list of supporting files."
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
            cache_ttl=CACHE_TTL_SKILLS,
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


class ReadSkillFilesTool(BaseTool):
    """
    Read supporting files from a skill directory.

    Efficiently retrieve one or more reference documents in a single call.
    Returns partial results if some files fail.

    Supports up to 5 files per batch to balance context size and iteration count.
    """

    MAX_FILES_PER_BATCH = 5

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
                "Read supporting files from a skill's directory. "
                "Returns partial results if some files are not found. "
                f"Supports 1-{self.MAX_FILES_PER_BATCH} files per call."
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
                            "List of relative filenames from 'available_files'. "
                            "Example: ['ALGORITHMS.md'] or ['GUIDE.md', 'CHECKLIST.md']"
                        ),
                        "minItems": 1,
                        "maxItems": self.MAX_FILES_PER_BATCH,
                    },
                },
                "required": ["skill_name", "filenames"],
            },
            category="skill",
            cache_ttl=CACHE_TTL_SKILLS,
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
                    f"You requested {len(filenames)} files. Split into multiple calls."
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
