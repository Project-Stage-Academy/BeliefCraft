"""
Unit tests for SkillStore.

Tests skill discovery, parsing, metadata caching, and security features.
"""

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from app.services.skill_store import ParsedSkill, SkillMetadata, SkillStore


@pytest.fixture
def temp_skills_dir() -> Generator[Path, None, None]:
    """Create temporary skills directory with test skills."""
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir)

        # Create valid skill
        skill1_dir = skills_dir / "test-skill-one"
        skill1_dir.mkdir()
        (skill1_dir / "SKILL.md").write_text(
            """---
name: test-skill-one
description: First test skill for unit testing
version: "1.0"
tags: [test, example]
dependencies: []
---

# Test Skill One

## When to Use
Use this for testing.

## Instructions
Step 1: Do something.
Step 2: Do something else.
""",
            encoding="utf-8",
        )

        # Create skill with supporting files
        skill2_dir = skills_dir / "test-skill-two-dir"
        skill2_dir.mkdir()
        (skill2_dir / "SKILL.md").write_text(
            """---
name: test-skill-two
description: Second test skill with supporting files
version: "2.0"
tags: [test, advanced]
---

# Test Skill Two

See GUIDE.md for details.
""",
            encoding="utf-8",
        )
        (skill2_dir / "GUIDE.md").write_text("# Guide\nDetailed guide here.", encoding="utf-8")
        (skill2_dir / "examples").mkdir()
        (skill2_dir / "examples" / "example1.md").write_text("Example content", encoding="utf-8")

        # Create invalid skill (missing name)
        invalid_dir = skills_dir / "invalid-skill"
        invalid_dir.mkdir()
        (invalid_dir / "SKILL.md").write_text(
            """---
description: Invalid skill missing name
---

# Invalid
""",
            encoding="utf-8",
        )

        # Create directory without SKILL.md (should be ignored)
        (skills_dir / "not-a-skill").mkdir()

        yield skills_dir


class TestSkillStoreDiscovery:
    """Test skill discovery and scanning."""

    def test_scan_discovers_valid_skills(self, temp_skills_dir: Path) -> None:
        """Test that scan discovers valid skills."""
        store = SkillStore(skills_dir=temp_skills_dir)
        skills = store.scan()

        assert len(skills) == 2
        assert "test-skill-one" in skills
        assert "test-skill-two" in skills
        assert "invalid-skill" not in skills
        assert "not-a-skill" not in skills

    def test_scan_caches_metadata(self, temp_skills_dir: Path) -> None:
        """Test that scan caches metadata in memory."""
        store = SkillStore(skills_dir=temp_skills_dir)

        # First scan
        skills1 = store.scan()
        assert len(skills1) == 2

        # Second scan should use cache
        skills2 = store.scan()
        assert skills1 is skills2  # Same object (cached)

    def test_get_skill_names(self, temp_skills_dir: Path) -> None:
        """Test get_skill_names returns sorted list."""
        store = SkillStore(skills_dir=temp_skills_dir)
        names = store.get_skill_names()

        assert names == ["test-skill-one", "test-skill-two"]
        assert names == sorted(names)

    def test_scan_with_missing_directory(self) -> None:
        """Test scan with non-existent skills directory."""
        store = SkillStore(skills_dir="/nonexistent/path")
        skills = store.scan()

        assert len(skills) == 0

    def test_enforce_name_matches_dir(self, temp_skills_dir: Path) -> None:
        """Test that skill name must match directory name."""
        # Create skill with mismatched name
        mismatch_dir = temp_skills_dir / "wrong-dir-name"
        mismatch_dir.mkdir()
        (mismatch_dir / "SKILL.md").write_text(
            """---
name: correct-name
description: Name doesn't match directory
---

# Mismatch
""",
            encoding="utf-8",
        )

        store = SkillStore(skills_dir=temp_skills_dir, enforce_name_matches_dir=True)
        skills = store.scan()

        # Should skip mismatched skill
        assert "wrong-dir-name" not in skills
        assert "correct-name" not in skills

    def test_scan_uses_frontmatter_name_as_canonical_key(self, temp_skills_dir: Path) -> None:
        """Test that frontmatter.name is the canonical skill identifier."""
        store = SkillStore(skills_dir=temp_skills_dir)
        skills = store.scan()

        assert "test-skill-two" in skills
        assert "test-skill-two-dir" not in skills
        assert skills["test-skill-two"].path is not None
        assert skills["test-skill-two"].path.parent.name == "test-skill-two-dir"

    def test_scan_rejects_duplicate_canonical_skill_names(self, temp_skills_dir: Path) -> None:
        """Test that duplicate frontmatter names are rejected to avoid aliasing."""
        duplicate_dir = temp_skills_dir / "zzz-duplicate"
        duplicate_dir.mkdir()
        (duplicate_dir / "SKILL.md").write_text(
            """---
name: test-skill-one
description: Duplicate skill that should not override the original
---

# Duplicate
""",
            encoding="utf-8",
        )

        store = SkillStore(skills_dir=temp_skills_dir)
        skills = store.scan()

        assert len(skills) == 2
        assert skills["test-skill-one"].description == "First test skill for unit testing"


class TestSkillStoreLoading:
    """Test skill content loading (Tier 2)."""

    def test_load_skill_success(self, temp_skills_dir: Path) -> None:
        """Test loading a valid skill."""
        store = SkillStore(skills_dir=temp_skills_dir)
        store.scan()

        parsed = store.load("test-skill-one")

        assert parsed is not None
        assert isinstance(parsed, ParsedSkill)
        assert parsed.metadata.name == "test-skill-one"
        assert parsed.metadata.description == "First test skill for unit testing"
        assert parsed.metadata.version == "1.0"
        assert "test" in parsed.metadata.tags
        assert "example" in parsed.metadata.tags
        assert "Test Skill One" in parsed.content
        assert "Step 1:" in parsed.content
        assert "---" not in parsed.content  # Frontmatter should be stripped

    def test_load_skill_by_canonical_name_when_directory_differs(
        self, temp_skills_dir: Path
    ) -> None:
        """Test loading a skill by frontmatter name when directory name differs."""
        store = SkillStore(skills_dir=temp_skills_dir)
        store.scan()

        parsed = store.load("test-skill-two")

        assert parsed is not None
        assert parsed.metadata.name == "test-skill-two"
        assert parsed.metadata.path is not None
        assert parsed.metadata.path.parent.name == "test-skill-two-dir"

    def test_load_skill_not_found(self, temp_skills_dir: Path) -> None:
        """Test loading non-existent skill."""
        store = SkillStore(skills_dir=temp_skills_dir)
        store.scan()

        parsed = store.load("nonexistent-skill")

        assert parsed is None

    def test_load_skill_caches_content(self, temp_skills_dir: Path) -> None:
        """Test that load caches parsed content."""
        store = SkillStore(skills_dir=temp_skills_dir)
        store.scan()

        parsed1 = store.load("test-skill-one")
        parsed2 = store.load("test-skill-one")

        assert parsed1 is parsed2  # Same object (cached)

    def test_load_skill_without_scan(self, temp_skills_dir: Path) -> None:
        """Test that load auto-scans if not already scanned."""
        store = SkillStore(skills_dir=temp_skills_dir)
        # Don't call scan()

        parsed = store.load("test-skill-one")

        assert parsed is not None
        assert parsed.metadata.name == "test-skill-one"


class TestSkillStoreSupportingFiles:
    """Test supporting file operations (Tier 3)."""

    def test_list_supporting_files(self, temp_skills_dir: Path) -> None:
        """Test listing supporting files for a skill."""
        store = SkillStore(skills_dir=temp_skills_dir)
        store.scan()

        files = store.list_supporting_files("test-skill-two")

        assert len(files) == 2
        assert "GUIDE.md" in files
        assert "examples/example1.md" in files
        assert all(isinstance(f, str) for f in files)

    def test_list_supporting_files_empty(self, temp_skills_dir: Path) -> None:
        """Test listing supporting files for skill with none."""
        store = SkillStore(skills_dir=temp_skills_dir)
        store.scan()

        files = store.list_supporting_files("test-skill-one")

        assert len(files) == 0

    def test_read_supporting_file_success(self, temp_skills_dir: Path) -> None:
        """Test reading a supporting file."""
        store = SkillStore(skills_dir=temp_skills_dir)
        store.scan()

        content = store.read_supporting_file("test-skill-two", "GUIDE.md")

        assert "# Guide" in content
        assert "Detailed guide here" in content

    def test_read_supporting_file_nested(self, temp_skills_dir: Path) -> None:
        """Test reading a nested supporting file."""
        store = SkillStore(skills_dir=temp_skills_dir)
        store.scan()

        content = store.read_supporting_file("test-skill-two", "examples/example1.md")

        assert "Example content" in content

    def test_read_supporting_file_not_found(self, temp_skills_dir: Path) -> None:
        """Test reading non-existent supporting file."""
        store = SkillStore(skills_dir=temp_skills_dir)
        store.scan()

        with pytest.raises(FileNotFoundError):
            store.read_supporting_file("test-skill-two", "nonexistent.md")

    def test_read_supporting_file_invalid_skill(self, temp_skills_dir: Path) -> None:
        """Test reading supporting file from non-existent skill."""
        store = SkillStore(skills_dir=temp_skills_dir)
        store.scan()

        with pytest.raises(ValueError, match="Skill not found"):
            store.read_supporting_file("nonexistent-skill", "GUIDE.md")


class TestSkillStoreSecurity:
    """Test security features (directory traversal prevention)."""

    def test_read_supporting_file_prevents_directory_traversal(self, temp_skills_dir: Path) -> None:
        """Test that directory traversal is prevented."""
        store = SkillStore(skills_dir=temp_skills_dir)
        store.scan()

        with pytest.raises(ValueError, match="path traversal"):
            store.read_supporting_file("test-skill-two", "../test-skill-one/SKILL.md")

    def test_read_supporting_file_prevents_absolute_paths(self, temp_skills_dir: Path) -> None:
        """Test that absolute paths are rejected."""
        store = SkillStore(skills_dir=temp_skills_dir)
        store.scan()

        with pytest.raises(ValueError, match="absolute path"):
            store.read_supporting_file("test-skill-two", "/etc/passwd")

    def test_read_supporting_file_prevents_empty_filename(self, temp_skills_dir: Path) -> None:
        """Test that empty filenames are rejected."""
        store = SkillStore(skills_dir=temp_skills_dir)
        store.scan()

        with pytest.raises(ValueError, match="empty"):
            store.read_supporting_file("test-skill-two", "")


class TestSkillStoreCatalog:
    """Test skill catalog generation."""

    def test_get_skill_catalog(self, temp_skills_dir: Path) -> None:
        """Test generating skill catalog XML."""
        store = SkillStore(skills_dir=temp_skills_dir)
        store.scan()

        catalog = store.get_skill_catalog()

        assert "<skill>" in catalog
        assert "<name>test-skill-one</name>" in catalog
        assert "<name>test-skill-two</name>" in catalog
        assert "<description>First test skill" in catalog
        assert "<tags>test, example</tags>" in catalog
        assert "<supporting_files>GUIDE.md, examples/example1.md</supporting_files>" in catalog

    def test_get_skill_catalog_empty(self) -> None:
        """Test catalog generation with no skills."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SkillStore(skills_dir=tmpdir)
            catalog = store.get_skill_catalog()

            assert catalog == "No skills available."

    def test_get_skill_catalog_escapes_html(self) -> None:
        """Test that catalog escapes HTML characters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir)
            skill_dir = skills_dir / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                """---
name: test-skill
description: Test with <html> & "quotes"
---

# Test
""",
                encoding="utf-8",
            )

            store = SkillStore(skills_dir=skills_dir)
            catalog = store.get_skill_catalog()

            assert "&lt;html&gt;" in catalog
            assert "&amp;" in catalog
            assert "&quot;" in catalog
            assert "<html>" not in catalog


class TestSkillStoreInvalidation:
    """Test cache invalidation."""

    def test_invalidate_clears_caches(self, temp_skills_dir: Path) -> None:
        """Test that invalidate clears all caches."""
        store = SkillStore(skills_dir=temp_skills_dir)
        store.scan()
        store.load("test-skill-one")

        assert len(store._metadata_cache) > 0
        assert len(store._content_cache) > 0

        store.invalidate()

        assert len(store._metadata_cache) == 0
        assert len(store._content_cache) == 0
        assert store._scanned is False

    def test_invalidate_forces_rescan(self, temp_skills_dir: Path) -> None:
        """Test that invalidate forces rescan on next access."""
        store = SkillStore(skills_dir=temp_skills_dir)
        skills1 = store.scan()

        store.invalidate()

        skills2 = store.scan()
        assert skills1 is not skills2  # Different objects after invalidation


class TestSkillMetadata:
    """Test SkillMetadata dataclass."""

    def test_from_dict_with_all_fields(self) -> None:
        """Test SkillMetadata.from_dict with all fields."""
        data = {
            "name": "test-skill",
            "description": "Test description",
            "version": "2.0",
            "tags": ["tag1", "tag2"],
            "dependencies": ["dep1"],
        }

        metadata = SkillMetadata.from_dict(data, path=Path("/test/SKILL.md"))

        assert metadata.name == "test-skill"
        assert metadata.description == "Test description"
        assert metadata.version == "2.0"
        assert metadata.tags == ("tag1", "tag2")
        assert metadata.dependencies == ("dep1",)
        assert metadata.path == Path("/test/SKILL.md")

    def test_from_dict_with_minimal_fields(self) -> None:
        """Test SkillMetadata.from_dict with minimal fields."""
        data = {"name": "test", "description": "desc"}

        metadata = SkillMetadata.from_dict(data, path=None)

        assert metadata.name == "test"
        assert metadata.description == "desc"
        assert metadata.version == "1.0"  # Default
        assert metadata.tags == ()
        assert metadata.dependencies == ()
        assert metadata.path is None

    def test_from_dict_filters_empty_strings(self) -> None:
        """Test that from_dict filters empty strings from tags/dependencies."""
        data = {
            "name": "test",
            "description": "desc",
            "tags": ["valid", "", "  ", "another"],
            "dependencies": ["", "dep1", "  "],
        }

        metadata = SkillMetadata.from_dict(data, path=None)

        assert metadata.tags == ("valid", "another")
        assert metadata.dependencies == ("dep1",)
