"""Skill store module for dynamic domain expertise management.

This module provides the infrastructure for the agent to discover and load
domain-specific diagnostic skills on demand.

Core components:
- SkillStore: Registry for skill discovery, metadata caching, and content loading
- SkillMetadata: Lightweight skill info (name, description, tags)
- ParsedSkill: Full skill content (metadata + markdown body)

Usage:
    ```python
    from app.services.skill_store import SkillStore
    from app.config import get_settings

    settings = get_settings()
    store = SkillStore(skills_dir=settings.SKILLS_DIR)

    # Tier 1: Discovery
    skills = store.scan()
    catalog = store.get_skill_catalog()

    # Tier 2: Activation
    skill = store.load("inventory-discrepancy-audit")
    if skill:
        print(skill.content)

    # Tier 3: Deep dive
    supporting_files = store.list_supporting_files("inventory-discrepancy-audit")
    if supporting_files:
        content = store.read_supporting_file(
            "inventory-discrepancy-audit",
            supporting_files[0]
        )
    ```
"""

from app.services.skill_store.store import (
    ParsedSkill,
    SkillMetadata,
    SkillStore,
    parse_metadata_only,
    parse_skill_file,
)

__all__ = [
    "SkillStore",
    "SkillMetadata",
    "ParsedSkill",
    "parse_metadata_only",
    "parse_skill_file",
]
