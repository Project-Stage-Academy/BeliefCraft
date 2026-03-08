"""
Unit tests for skill management tools.

Tests LoadSkillTool, ReadSkillFileTool, and ReadSkillFilesTool functionality.
"""

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from app.services.skill_store import SkillStore
from app.tools.base import ToolMetadata
from app.tools.skill_tools import LoadSkillTool, ReadSkillFilesTool, ReadSkillFileTool


@pytest.fixture
def temp_skills_dir() -> Generator[Path, None, None]:
    """Create temporary skills directory with test skills."""
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir)

        # Create skill with supporting files
        skill_dir = skills_dir / "test-diagnostic-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            """---
name: test-diagnostic-skill
description: Test diagnostic workflow for unit testing
version: "1.0"
tags: [test, diagnostic, example]
dependencies: []
---

# Test Diagnostic Skill

## When to Use
Use this when testing diagnostic workflows.

## Instructions
Step 1: Analyze the situation.
Step 2: Use appropriate tools.
Step 3: Formulate recommendations.

## Example
Test example here.
""",
            encoding="utf-8",
        )
        (skill_dir / "CHECKLIST.md").write_text("# Checklist\n- Item 1\n- Item 2", encoding="utf-8")
        (skill_dir / "ALGORITHMS.md").write_text(
            "# Algorithms\nAlgorithm details", encoding="utf-8"
        )

        # Create second skill
        skill2_dir = skills_dir / "another-skill"
        skill2_dir.mkdir()
        (skill2_dir / "SKILL.md").write_text(
            """---
name: another-skill
description: Another test skill
---

# Another Skill
Content here.
""",
            encoding="utf-8",
        )

        yield skills_dir


@pytest.fixture
def skill_store(temp_skills_dir: Path) -> SkillStore:
    """Create SkillStore with test skills."""
    store = SkillStore(skills_dir=temp_skills_dir)
    store.scan()
    return store


class TestLoadSkillTool:
    """Test LoadSkillTool functionality."""

    def test_get_metadata(self, skill_store: SkillStore) -> None:
        """Test that metadata includes skill list."""
        tool = LoadSkillTool(skill_store)
        metadata = tool.get_metadata()

        assert isinstance(metadata, ToolMetadata)
        assert metadata.name == "load_skill"
        assert metadata.category == "skill"
        assert metadata.cache_ttl == 86400  # 24 hours
        assert metadata.skip_cache is False

        # Description should include available skills
        assert "another-skill" in metadata.description
        assert "test-diagnostic-skill" in metadata.description

        # Parameters schema
        assert metadata.parameters["type"] == "object"
        assert "skill_name" in metadata.parameters["properties"]
        assert "skill_name" in metadata.parameters["required"]

    @pytest.mark.asyncio
    async def test_execute_success(self, skill_store: SkillStore) -> None:
        """Test successful skill loading."""
        tool = LoadSkillTool(skill_store)

        result = await tool.execute(skill_name="test-diagnostic-skill")

        assert isinstance(result, dict)
        assert result["skill_name"] == "test-diagnostic-skill"
        assert result["description"] == "Test diagnostic workflow for unit testing"
        assert result["version"] == "1.0"
        assert "test" in result["tags"]
        assert "diagnostic" in result["tags"]
        assert "Test Diagnostic Skill" in result["instructions"]
        assert "Step 1:" in result["instructions"]
        assert "Step 2:" in result["instructions"]
        assert len(result["available_files"]) == 2
        assert "CHECKLIST.md" in result["available_files"]
        assert "ALGORITHMS.md" in result["available_files"]

    @pytest.mark.asyncio
    async def test_execute_skill_not_found(self, skill_store: SkillStore) -> None:
        """Test loading non-existent skill."""
        tool = LoadSkillTool(skill_store)

        result = await tool.execute(skill_name="nonexistent-skill")

        assert isinstance(result, dict)
        assert "error" in result
        assert "nonexistent-skill" in result["error"]
        assert "available_skills" in result
        assert isinstance(result["available_skills"], list)
        assert "test-diagnostic-skill" in result["available_skills"]
        assert "message" in result

    @pytest.mark.asyncio
    async def test_execute_with_extra_kwargs(self, skill_store: SkillStore) -> None:
        """Test that extra kwargs are ignored."""
        tool = LoadSkillTool(skill_store)

        result = await tool.execute(
            skill_name="test-diagnostic-skill", extra_param="ignored", another="also_ignored"
        )

        assert "error" not in result
        assert result["skill_name"] == "test-diagnostic-skill"

    def test_metadata_updates_with_skill_names(self, temp_skills_dir: Path) -> None:
        """Test that metadata reflects current skill names."""
        store = SkillStore(skills_dir=temp_skills_dir)
        store.scan()
        tool = LoadSkillTool(store)

        metadata_before = tool.get_metadata()
        assert "test-diagnostic-skill" in metadata_before.description

        # Add new skill
        new_skill_dir = temp_skills_dir / "new-skill"
        new_skill_dir.mkdir()
        (new_skill_dir / "SKILL.md").write_text(
            """---
name: new-skill
description: Newly added skill
---

# New Skill
""",
            encoding="utf-8",
        )

        # Invalidate and rescan
        store.invalidate()
        store.scan()

        # Create new tool instance
        tool_after = LoadSkillTool(store)
        metadata_after = tool_after.get_metadata()

        assert "new-skill" in metadata_after.description


class TestReadSkillFileTool:
    """Test ReadSkillFileTool functionality."""

    def test_get_metadata(self, skill_store: SkillStore) -> None:
        """Test that metadata includes skill list."""
        tool = ReadSkillFileTool(skill_store)
        metadata = tool.get_metadata()

        assert isinstance(metadata, ToolMetadata)
        assert metadata.name == "read_skill_file"
        assert metadata.category == "skill"
        assert metadata.cache_ttl == 86400  # 24 hours
        assert metadata.skip_cache is False

        # Description should include available skills
        assert "another-skill" in metadata.description
        assert "test-diagnostic-skill" in metadata.description

        # Parameters schema
        assert metadata.parameters["type"] == "object"
        assert "skill_name" in metadata.parameters["properties"]
        assert "filename" in metadata.parameters["properties"]
        assert "skill_name" in metadata.parameters["required"]
        assert "filename" in metadata.parameters["required"]

    @pytest.mark.asyncio
    async def test_execute_success(self, skill_store: SkillStore) -> None:
        """Test successful file reading."""
        tool = ReadSkillFileTool(skill_store)

        result = await tool.execute(skill_name="test-diagnostic-skill", filename="CHECKLIST.md")

        assert isinstance(result, dict)
        assert result["skill_name"] == "test-diagnostic-skill"
        assert result["filename"] == "CHECKLIST.md"
        assert "# Checklist" in result["content"]
        assert "- Item 1" in result["content"]
        assert "- Item 2" in result["content"]

    @pytest.mark.asyncio
    async def test_execute_file_not_found(self, skill_store: SkillStore) -> None:
        """Test reading non-existent file."""
        tool = ReadSkillFileTool(skill_store)

        result = await tool.execute(skill_name="test-diagnostic-skill", filename="NONEXISTENT.md")

        assert isinstance(result, dict)
        assert "error" in result
        assert "NONEXISTENT.md" not in result.get("content", "")
        assert "available_files" in result
        assert isinstance(result["available_files"], list)
        assert "CHECKLIST.md" in result["available_files"]
        assert "message" in result

    @pytest.mark.asyncio
    async def test_execute_skill_not_found(self, skill_store: SkillStore) -> None:
        """Test reading file from non-existent skill."""
        tool = ReadSkillFileTool(skill_store)

        result = await tool.execute(skill_name="nonexistent-skill", filename="GUIDE.md")

        assert isinstance(result, dict)
        assert "error" in result
        assert "nonexistent-skill" not in result.get("content", "")

    @pytest.mark.asyncio
    async def test_execute_prevents_directory_traversal(self, skill_store: SkillStore) -> None:
        """Test that directory traversal is prevented."""
        tool = ReadSkillFileTool(skill_store)

        result = await tool.execute(
            skill_name="test-diagnostic-skill", filename="../another-skill/SKILL.md"
        )

        assert isinstance(result, dict)
        assert "error" in result
        assert "invalid" in result["error"].lower() or "security" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_execute_prevents_absolute_paths(self, skill_store: SkillStore) -> None:
        """Test that absolute paths are rejected."""
        tool = ReadSkillFileTool(skill_store)

        result = await tool.execute(skill_name="test-diagnostic-skill", filename="/etc/passwd")

        assert isinstance(result, dict)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_with_extra_kwargs(self, skill_store: SkillStore) -> None:
        """Test that extra kwargs are ignored."""
        tool = ReadSkillFileTool(skill_store)

        result = await tool.execute(
            skill_name="test-diagnostic-skill",
            filename="CHECKLIST.md",
            extra_param="ignored",
        )

        assert "error" not in result
        assert "# Checklist" in result["content"]


class TestReadSkillFilesTool:
    """Test ReadSkillFilesTool batch functionality."""

    def test_get_metadata(self, skill_store: SkillStore) -> None:
        """Test that metadata includes skill list and max batch size."""
        tool = ReadSkillFilesTool(skill_store)
        metadata = tool.get_metadata()

        assert isinstance(metadata, ToolMetadata)
        assert metadata.name == "read_skill_files"
        assert metadata.category == "skill"
        assert metadata.cache_ttl == 86400  # 24 hours
        assert metadata.skip_cache is False

        # Description should mention batch and max files
        assert "multiple" in metadata.description.lower()
        assert str(ReadSkillFilesTool.MAX_FILES_PER_BATCH) in metadata.description

        # Parameters schema
        assert metadata.parameters["type"] == "object"
        assert "skill_name" in metadata.parameters["properties"]
        assert "filenames" in metadata.parameters["properties"]
        assert metadata.parameters["properties"]["filenames"]["type"] == "array"
        assert (
            metadata.parameters["properties"]["filenames"]["maxItems"]
            == ReadSkillFilesTool.MAX_FILES_PER_BATCH
        )

    @pytest.mark.asyncio
    async def test_read_multiple_files_success(self, skill_store: SkillStore) -> None:
        """Test reading multiple files successfully."""
        tool = ReadSkillFilesTool(skill_store)

        result = await tool.execute(
            skill_name="test-diagnostic-skill",
            filenames=["CHECKLIST.md", "ALGORITHMS.md"],
        )

        assert result["skill_name"] == "test-diagnostic-skill"
        assert result["files_requested"] == 2
        assert result["files_success"] == 2
        assert result["files_failed"] == 0

        assert "success" in result
        assert "CHECKLIST.md" in result["success"]
        assert "ALGORITHMS.md" in result["success"]
        assert "# Checklist" in result["success"]["CHECKLIST.md"]
        assert "# Algorithms" in result["success"]["ALGORITHMS.md"]

        assert "errors" not in result

    @pytest.mark.asyncio
    async def test_read_files_partial_success(self, skill_store: SkillStore) -> None:
        """Test partial success when some files don't exist."""
        tool = ReadSkillFilesTool(skill_store)

        result = await tool.execute(
            skill_name="test-diagnostic-skill",
            filenames=["CHECKLIST.md", "MISSING.md", "ALGORITHMS.md"],
        )

        assert result["skill_name"] == "test-diagnostic-skill"
        assert result["files_requested"] == 3
        assert result["files_success"] == 2
        assert result["files_failed"] == 1

        # Successful reads
        assert "success" in result
        assert "CHECKLIST.md" in result["success"]
        assert "ALGORITHMS.md" in result["success"]

        # Failed reads
        assert "errors" in result
        assert "MISSING.md" in result["errors"]
        assert "not found" in result["errors"]["MISSING.md"].lower()

        # Helper info
        assert "available_files" in result

    @pytest.mark.asyncio
    async def test_read_files_all_fail(self, skill_store: SkillStore) -> None:
        """Test when all files fail to read."""
        tool = ReadSkillFilesTool(skill_store)

        result = await tool.execute(
            skill_name="test-diagnostic-skill",
            filenames=["MISSING1.md", "MISSING2.md"],
        )

        assert result["files_requested"] == 2
        assert result["files_success"] == 0
        assert result["files_failed"] == 2

        assert "success" not in result
        assert "errors" in result
        assert len(result["errors"]) == 2

    @pytest.mark.asyncio
    async def test_read_files_exceeds_max_batch(self, skill_store: SkillStore) -> None:
        """Test error when requesting too many files."""
        tool = ReadSkillFilesTool(skill_store)

        result = await tool.execute(
            skill_name="test-diagnostic-skill",
            filenames=["file1.md", "file2.md", "file3.md", "file4.md"],  # 4 files > max 3
        )

        assert "error" in result
        assert "too many" in result["error"].lower()
        assert "max_batch_size" in result
        assert result["max_batch_size"] == ReadSkillFilesTool.MAX_FILES_PER_BATCH

    @pytest.mark.asyncio
    async def test_read_files_empty_list(self, skill_store: SkillStore) -> None:
        """Test error when filenames list is empty."""
        tool = ReadSkillFilesTool(skill_store)

        result = await tool.execute(
            skill_name="test-diagnostic-skill",
            filenames=[],
        )

        assert "error" in result
        assert "empty" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_read_files_invalid_skill(self, skill_store: SkillStore) -> None:
        """Test error when skill doesn't exist."""
        tool = ReadSkillFilesTool(skill_store)

        result = await tool.execute(
            skill_name="nonexistent-skill",
            filenames=["any.md"],
        )

        assert result["files_failed"] > 0
        assert "errors" in result

    @pytest.mark.asyncio
    async def test_read_files_directory_traversal_attempt(self, skill_store: SkillStore) -> None:
        """Test security: directory traversal prevention."""
        tool = ReadSkillFilesTool(skill_store)

        result = await tool.execute(
            skill_name="test-diagnostic-skill",
            filenames=["../../../etc/passwd", "CHECKLIST.md"],
        )

        # Should be partial success
        assert result["files_success"] == 1  # CHECKLIST.md
        assert result["files_failed"] == 1  # ../../../etc/passwd

        assert "CHECKLIST.md" in result["success"]
        assert "../../../etc/passwd" in result["errors"]
        assert "invalid" in result["errors"]["../../../etc/passwd"].lower()

    @pytest.mark.asyncio
    async def test_read_files_single_file(self, skill_store: SkillStore) -> None:
        """Test reading single file (edge case for batch tool)."""
        tool = ReadSkillFilesTool(skill_store)

        result = await tool.execute(
            skill_name="test-diagnostic-skill",
            filenames=["CHECKLIST.md"],
        )

        assert result["files_requested"] == 1
        assert result["files_success"] == 1
        assert result["files_failed"] == 0
        assert "CHECKLIST.md" in result["success"]

    @pytest.mark.asyncio
    async def test_read_files_ignores_extra_kwargs(self, skill_store: SkillStore) -> None:
        """Test that extra kwargs don't break execution."""
        tool = ReadSkillFilesTool(skill_store)

        result = await tool.execute(
            skill_name="test-diagnostic-skill",
            filenames=["CHECKLIST.md"],
            extra_param="ignored",
        )

        assert result["files_success"] == 1
        assert "CHECKLIST.md" in result["success"]


class TestSkillToolsIntegration:
    """Test integration between LoadSkillTool and ReadSkillFileTool."""

    @pytest.mark.asyncio
    async def test_workflow_load_then_read(self, skill_store: SkillStore) -> None:
        """Test typical workflow: load skill, then read supporting file."""
        load_tool = LoadSkillTool(skill_store)
        read_tool = ReadSkillFileTool(skill_store)

        # Step 1: Load skill
        load_result = await load_tool.execute(skill_name="test-diagnostic-skill")

        assert "available_files" in load_result
        assert "CHECKLIST.md" in load_result["available_files"]

        # Step 2: Read supporting file from available_files
        filename = load_result["available_files"][0]
        read_result = await read_tool.execute(skill_name="test-diagnostic-skill", filename=filename)

        assert read_result["filename"] == filename
        assert "content" in read_result

    @pytest.mark.asyncio
    async def test_multiple_skills_isolation(self, skill_store: SkillStore) -> None:
        """Test that skills are properly isolated."""
        load_tool = LoadSkillTool(skill_store)

        # Load both skills
        result1 = await load_tool.execute(skill_name="test-diagnostic-skill")
        result2 = await load_tool.execute(skill_name="another-skill")

        assert result1["skill_name"] != result2["skill_name"]
        assert result1["description"] != result2["description"]
        assert len(result1["available_files"]) > 0
        assert len(result2["available_files"]) == 0


class TestSkillToolsWithEmptyStore:
    """Test skill tools with empty skill store."""

    @pytest.fixture
    def empty_store(self) -> Generator[SkillStore, None, None]:
        """Create empty SkillStore."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SkillStore(skills_dir=tmpdir)
            store.scan()
            yield store

    def test_load_tool_metadata_with_no_skills(self, empty_store: SkillStore) -> None:
        """Test LoadSkillTool metadata when no skills available."""
        tool = LoadSkillTool(empty_store)
        metadata = tool.get_metadata()

        assert "none" in metadata.description.lower() or metadata.description == ""

    @pytest.mark.asyncio
    async def test_load_tool_execute_with_no_skills(self, empty_store: SkillStore) -> None:
        """Test LoadSkillTool execution when no skills available."""
        tool = LoadSkillTool(empty_store)

        result = await tool.execute(skill_name="any-skill")

        assert "error" in result
        assert isinstance(result.get("available_skills"), list)
        assert len(result["available_skills"]) == 0
