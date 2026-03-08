"""Skill store and loader for dynamic skill management.

This module implements the **domain skills system** for the agent-service.

A *skill* is a self-contained package stored as a directory on disk:

- ``SKILL.md`` (required) — YAML frontmatter (metadata) + markdown body (instructions).
- Supporting files (optional) — additional ``.md`` files referenced by SKILL.md.

Progressive disclosure (3 tiers):
1) Discovery: scan skills root, parse YAML frontmatter only, cache metadata in-memory.
2) Activation: load full SKILL.md body on demand for a single skill.
3) Deep dive: read supporting files on demand.

Security:
- SkillStore is anchored to a configured root dir.
- Supporting file reads prevent directory traversal and absolute paths.

Caching:
- SkillStore does only in-process caching (metadata + loaded skill bodies).
- Redis caching should be applied at the tool layer via CachedTool wrapper.
"""

from __future__ import annotations

import html
import re
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from common.logging import get_logger

logger = get_logger(__name__)


_FRONTMATTER_RE = re.compile(
    r"^\ufeff?---\s*\n(.*?)\n---\s*\n(.*)$",
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SkillMetadata:
    """Lightweight metadata extracted from SKILL.md YAML frontmatter."""

    name: str
    description: str
    version: str = "1.0"
    tags: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    path: Path | None = None  # absolute path to SKILL.md

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, path: Path | None) -> SkillMetadata:
        tags = data.get("tags") or []
        dependencies = data.get("dependencies") or []
        return cls(
            name=str(data.get("name") or "").strip(),
            description=str(data.get("description") or "").strip(),
            version=str(data.get("version") or "1.0").strip(),
            tags=tuple(str(t).strip() for t in tags if str(t).strip()),
            dependencies=tuple(str(d).strip() for d in dependencies if str(d).strip()),
            path=path,
        )


@dataclass(frozen=True, slots=True)
class ParsedSkill:
    """Fully parsed skill: metadata + markdown body (no frontmatter)."""

    metadata: SkillMetadata
    content: str


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_frontmatter_and_body(text: str, *, file_path: Path) -> tuple[dict[str, Any], str]:
    """Parse a SKILL.md document into (frontmatter_dict, body).

    Raises:
        ValueError: if YAML frontmatter is missing or invalid.
    """
    match = _FRONTMATTER_RE.match(text.strip())
    if not match:
        raise ValueError(f"Invalid SKILL.md format (missing YAML frontmatter): {file_path}")

    frontmatter_yaml, body = match.groups()
    try:
        frontmatter_data = yaml.safe_load(frontmatter_yaml) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in frontmatter: {file_path}: {e}") from e

    if not isinstance(frontmatter_data, dict):
        raise ValueError(f"Frontmatter must be a YAML mapping/dict: {file_path}")

    return frontmatter_data, body.strip()


def parse_metadata_only(file_path: Path) -> SkillMetadata:
    """Parse only YAML frontmatter from SKILL.md."""
    if not file_path.exists():
        raise FileNotFoundError(f"Skill file not found: {file_path}")

    text = file_path.read_text(encoding="utf-8")
    frontmatter, _ = _parse_frontmatter_and_body(text, file_path=file_path)
    return SkillMetadata.from_dict(frontmatter, path=file_path)


def parse_skill_file(file_path: Path) -> ParsedSkill:
    """Parse full SKILL.md (frontmatter + body)."""
    if not file_path.exists():
        raise FileNotFoundError(f"Skill file not found: {file_path}")

    text = file_path.read_text(encoding="utf-8")
    frontmatter, body = _parse_frontmatter_and_body(text, file_path=file_path)
    metadata = SkillMetadata.from_dict(frontmatter, path=file_path)
    return ParsedSkill(metadata=metadata, content=body)


def _validate_relative_posix_path(filename: str) -> PurePosixPath:
    """Validate a tool-provided filename as a safe relative POSIX path.

    We intentionally treat tool inputs as POSIX paths ("/" separators),
    regardless of platform, to avoid Windows edge cases.

    Rules:
    - must not be empty
    - must not be absolute
    - must not contain ".."
    """
    name = filename.strip()
    if not name:
        raise ValueError("Invalid filename: empty")

    p = PurePosixPath(name)

    if p.is_absolute():
        raise ValueError(f"Invalid filename (absolute paths are not allowed): {filename}")

    if any(part == ".." for part in p.parts):
        raise ValueError(f"Invalid filename (path traversal '..' is not allowed): {filename}")

    return p


def _safe_join_under_dir(root_dir: Path, relative_posix: PurePosixPath) -> Path:
    """Join root_dir with a validated PurePosixPath and ensure it stays under root_dir."""
    # Convert POSIX path to system path segments.
    candidate = root_dir.joinpath(*relative_posix.parts).resolve()
    root_resolved = root_dir.resolve()

    try:
        candidate.relative_to(root_resolved)
    except ValueError as e:
        raise ValueError(f"Invalid filename (escapes skill directory): {relative_posix}") from e

    return candidate


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class SkillStore:
    """Skill registry with progressive disclosure and in-process caching.

    Notes:
    - The store is intentionally synchronous (disk IO). Call from a threadpool if needed.
    - Redis caching should be applied at the tool layer (CachedTool wrapper).
    """

    def __init__(
        self,
        skills_dir: str | Path,
        *,
        enforce_name_matches_dir: bool = True,
        allowed_root: str | Path | None = None,
    ) -> None:
        self.skills_dir = Path(skills_dir).resolve()
        self.enforce_name_matches_dir = enforce_name_matches_dir

        # Optional guardrail: ensure skills_dir is inside allowed_root (e.g., agent-service/app).
        self.allowed_root = Path(allowed_root).resolve() if allowed_root is not None else None
        if self.allowed_root is not None:
            try:
                self.skills_dir.relative_to(self.allowed_root)
            except ValueError as e:
                raise ValueError(
                    f"skills_dir must be inside allowed_root. skills_dir={self.skills_dir} "
                    f"allowed_root={self.allowed_root}"
                ) from e

        self._metadata_cache: dict[str, SkillMetadata] = {}
        self._content_cache: dict[str, ParsedSkill] = {}
        self._scanned = False

    # -------------------- Discovery (Tier 1) --------------------

    def scan(self) -> dict[str, SkillMetadata]:
        """Discover skills by scanning for directories containing SKILL.md.

        Contract:
        - skill directory name must be kebab-case (recommended; not enforced here).
        - YAML 'name' must match directory name if enforce_name_matches_dir=True.
        - Only directories with direct child SKILL.md are treated as skills.
          (We do not rglob SKILL.md everywhere, to avoid unexpected discovery.)
        """
        if self._scanned and self._metadata_cache:
            logger.info(
                "skill_catalog_scan_cache_hit",
                tier=1,
                skills_count=len(self._metadata_cache),
            )
            return self._metadata_cache

        scan_start = time.perf_counter()
        self._metadata_cache.clear()
        self._content_cache.clear()

        if not self.skills_dir.exists():
            logger.warning(
                "skills_directory_not_found",
                skills_dir=str(self.skills_dir),
            )
            logger.info(
                "skill_catalog_scan_complete",
                tier=1,
                duration_ms=int((time.perf_counter() - scan_start) * 1000),
                skills_count=0,
            )
            self._scanned = True
            return self._metadata_cache

        # Discover only direct skill folders: skills_dir/*/SKILL.md
        for skill_dir in sorted(p for p in self.skills_dir.iterdir() if p.is_dir()):
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue

            try:
                metadata = parse_metadata_only(skill_file)
                if not metadata.name:
                    raise ValueError("Missing required frontmatter field: name")
                if not metadata.description:
                    raise ValueError("Missing required frontmatter field: description")

                dir_name = skill_dir.name
                if self.enforce_name_matches_dir and metadata.name != dir_name:
                    raise ValueError(
                        f"Skill frontmatter name must match directory name. "
                        f"name={metadata.name!r} dir={dir_name!r}"
                    )

                # Cache key is the directory name (== metadata.name when enforced).
                # This keeps tool calls stable and avoids aliasing.
                self._metadata_cache[dir_name] = SkillMetadata(
                    name=metadata.name,
                    description=metadata.description,
                    version=metadata.version,
                    tags=metadata.tags,
                    dependencies=metadata.dependencies,
                    path=skill_file.resolve(),
                )
                logger.debug(
                    "skill_registered",
                    skill_name=dir_name,
                    version=metadata.version,
                )
            except Exception as e:
                logger.warning(
                    "skill_registration_failed",
                    skill_file=str(skill_file),
                    error=str(e),
                    error_type=type(e).__name__,
                )

        self._scanned = True
        logger.info(
            "skill_catalog_scan_complete",
            tier=1,
            duration_ms=int((time.perf_counter() - scan_start) * 1000),
            skills_count=len(self._metadata_cache),
            skills_dir=str(self.skills_dir),
        )
        return self._metadata_cache

    def get_skill_names(self) -> list[str]:
        if not self._scanned:
            self.scan()
        return sorted(self._metadata_cache.keys())

    # -------------------- Activation (Tier 2) --------------------

    def load(self, skill_name: str) -> ParsedSkill | None:
        """Load SKILL.md body for a skill by name (directory name)."""
        load_start = time.perf_counter()

        if skill_name in self._content_cache:
            logger.info(
                "skill_load_cache_hit",
                tier=2,
                skill=skill_name,
                duration_ms=int((time.perf_counter() - load_start) * 1000),
            )
            return self._content_cache[skill_name]

        if not self._scanned:
            self.scan()

        metadata = self._metadata_cache.get(skill_name)
        if not metadata or not metadata.path:
            logger.warning(
                "skill_load_not_found",
                tier=2,
                skill=skill_name,
            )
            return None

        try:
            parsed = parse_skill_file(metadata.path)
            # Enforce again at load time to avoid tampering after scan.
            if self.enforce_name_matches_dir and parsed.metadata.name != skill_name:
                raise ValueError(
                    f"Skill frontmatter name must match directory name. "
                    f"name={parsed.metadata.name!r} dir={skill_name!r}"
                )
            self._content_cache[skill_name] = parsed
            logger.info(
                "skill_load_cache_miss",
                tier=2,
                skill=skill_name,
                duration_ms=int((time.perf_counter() - load_start) * 1000),
                content_length=len(parsed.content),
            )
            return parsed
        except Exception as e:
            logger.error(
                "skill_load_error",
                tier=2,
                skill=skill_name,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            return None

    def list_supporting_files(self, skill_name: str) -> list[str]:
        """List supporting markdown files under the skill directory (relative POSIX paths)."""
        if not self._scanned:
            self.scan()

        metadata = self._metadata_cache.get(skill_name)
        if not metadata or not metadata.path:
            return []

        skill_dir = metadata.path.parent
        files: list[str] = []
        for f in skill_dir.rglob("*.md"):
            if f.is_file() and f.name != "SKILL.md":
                # Convert to relative POSIX path
                relative_path = f.relative_to(skill_dir).as_posix()
                files.append(relative_path)
        return sorted(set(files))

    # -------------------- Deep dive (Tier 3) --------------------

    def read_supporting_file(self, skill_name: str, filename: str) -> str:
        """Read a supporting file under a skill directory.

        Raises:
            ValueError: invalid skill or invalid filename.
            FileNotFoundError: missing file.
        """
        read_start = time.perf_counter()
        if not self._scanned:
            self.scan()

        metadata = self._metadata_cache.get(skill_name)
        if not metadata or not metadata.path:
            logger.warning(
                "supporting_file_skill_not_found",
                tier=3,
                skill=skill_name,
                file=filename,
            )
            raise ValueError(f"Skill not found: {skill_name}")

        skill_dir = metadata.path.parent
        rel = _validate_relative_posix_path(filename)
        file_path = _safe_join_under_dir(skill_dir, rel)

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {skill_name}/{filename}")

        content = file_path.read_text(encoding="utf-8")
        logger.info(
            "supporting_file_read",
            tier=3,
            skill=skill_name,
            file=filename,
            duration_ms=int((time.perf_counter() - read_start) * 1000),
            content_length=len(content),
        )
        return content

    # -------------------- Catalog rendering --------------------

    def get_skill_catalog(self) -> str:
        """Generate an XML-ish catalog string for system prompt injection.

        The output is escaped to avoid breaking XML if descriptions contain
        '<', '>', '&', etc.
        """
        if not self._scanned:
            self.scan()
        if not self._metadata_cache:
            return "No skills available."

        render_start = time.perf_counter()
        lines: list[str] = []

        for name, metadata in sorted(self._metadata_cache.items()):
            lines.append("<skill>")
            lines.append(f"  <name>{html.escape(name)}</name>")
            lines.append(f"  <description>{html.escape(metadata.description)}</description>")
            if metadata.tags:
                lines.append(f"  <tags>{html.escape(', '.join(metadata.tags))}</tags>")
            # Optional: include file names (still Tier 1 lightweight)
            supporting = self.list_supporting_files(name)
            if supporting:
                lines.append(
                    f"  <supporting_files>{html.escape(', '.join(supporting))}</supporting_files>"
                )
            lines.append("</skill>")

        catalog = "\n".join(lines)
        logger.info(
            "skill_catalog_rendered",
            tier=1,
            duration_ms=int((time.perf_counter() - render_start) * 1000),
            skills_count=len(self._metadata_cache),
            catalog_length=len(catalog),
        )
        return catalog

    # -------------------- Maintenance --------------------

    def invalidate(self) -> None:
        """Clear in-process caches and force a rescan on next access.

        Note: Redis/tool caching is separate and must be invalidated elsewhere
        (or disabled in development).
        """
        self._metadata_cache = {}
        self._content_cache = {}
        self._scanned = False
        logger.info("skill_store_cache_invalidated")
