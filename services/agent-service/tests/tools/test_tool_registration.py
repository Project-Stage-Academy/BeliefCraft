# file: services/agent-service/tests/test_tool_registration.py
"""
Unit tests for tool registration.

Tests automatic registration of environment tools at import time.
RAG tools are now loaded dynamically via MCP server during startup
(see test_mcp_tools.py for MCP tool loading tests).
Skill tools are loaded dynamically via register_skill_tools() during startup.
"""

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from app.tools.cached_tool import CachedTool
from app.tools.factory import ToolRegistryFactory
from app.tools.registration import register_skill_tools


class TestToolRegistration:
    """Test automatic tool registration on import."""

    @pytest.fixture
    def registry(self):
        return ToolRegistryFactory.create_env_sub_agent_registry()

    def test_environment_tools_registered_on_import(self, registry) -> None:
        """Test that 21 environment tools are auto-registered on import."""
        environment_tool_count = sum(
            1 for t in registry.tools.values() if t.get_metadata().category == "environment"
        )

        assert environment_tool_count == 21, (
            f"Expected 21 environment tools, got {environment_tool_count}. "
            "Environment tools should be auto-registered on import."
        )

    def test_environment_tools_registered(self, registry) -> None:
        """Test that all 21 environment tools are registered."""
        environment_tools = [
            "list_suppliers",
            "get_supplier",
            "list_purchase_orders",
            "get_purchase_order",
            "list_po_lines",
            "get_procurement_pipeline_summary",
            "list_inventory_moves",
            "get_inventory_move",
            "get_inventory_move_audit_trace",
            "get_inventory_adjustments_summary",
            "list_warehouses",
            "get_warehouse",
            "list_locations",
            "get_location",
            "get_locations_tree",
            "get_capacity_utilization_snapshot",
            "list_sensor_devices",
            "get_sensor_device",
            "get_device_health_summary",
            "get_device_anomalies",
            "get_observed_inventory_snapshot",
        ]

        assert len(environment_tools) == len(set(environment_tools)), (
            f"Tool list contains duplicates: "
            f"{[t for t in environment_tools if environment_tools.count(t) > 1]}"
        )

        registered_env_tools = {
            name
            for name, tool in registry.tools.items()
            if tool.get_metadata().category == "environment"
        }
        expected_tools = set(environment_tools)

        assert registered_env_tools == expected_tools, (
            f"Registry mismatch:\n"
            f"  Missing from registry: {expected_tools - registered_env_tools}\n"
            f"  Unexpected in registry: {registered_env_tools - expected_tools}"
        )

        for tool_name in environment_tools:
            tool = registry.get_tool(tool_name)
            assert tool is not None
            assert isinstance(tool, CachedTool)
            assert tool.get_metadata().category == "environment"

    def test_rag_tools_not_registered_on_import(self, registry) -> None:
        """Test that RAG tools are NOT auto-registered (they come from MCP)."""
        deprecated_rag_tools = [
            "search_knowledge_base",
            "expand_graph_by_ids",
            "get_entity_by_number",
        ]

        for tool_name in deprecated_rag_tools:
            with pytest.raises(
                Exception,
                match=r"Tool .* not found",
            ):
                registry.get_tool(tool_name)

    def test_real_time_tools_skip_cache(self, registry) -> None:
        """Test that real-time tools have skip_cache=True."""
        real_time_tools = [
            "get_observed_inventory_snapshot",
        ]

        for tool_name in real_time_tools:
            tool = registry.get_tool(tool_name)
            metadata = tool.get_metadata()
            assert metadata.skip_cache is True, f"{tool_name} should skip cache"

    def test_cached_environment_tools_have_ttl(self, registry) -> None:
        """Test that cached environment tools have appropriate TTL."""
        cached_tools_ttl = {
            "list_purchase_orders": 300,
            "list_po_lines": 300,
            "get_procurement_pipeline_summary": 600,
            "get_capacity_utilization_snapshot": 600,
            "list_inventory_moves": 3600,
            "get_inventory_move_audit_trace": 3600,
        }

        for tool_name, expected_ttl in cached_tools_ttl.items():
            tool = registry.get_tool(tool_name)
            metadata = tool.get_metadata()
            assert (
                metadata.cache_ttl == expected_ttl
            ), f"{tool_name} should have TTL={expected_ttl}, got {metadata.cache_ttl}"

    def test_all_registered_tools_wrapped_in_cached_tool(self, registry) -> None:
        """Test that all registered tools are wrapped in CachedTool."""
        for tool_name, tool in registry.tools.items():
            assert isinstance(tool, CachedTool), f"{tool_name} should be wrapped in CachedTool"

    def test_environment_tool_metadata_passthrough(self, registry) -> None:
        """Test that CachedTool properly passes through metadata for environment tools."""
        tool = registry.get_tool("get_observed_inventory_snapshot")
        metadata = tool.get_metadata()

        assert metadata.name == "get_observed_inventory_snapshot"
        assert metadata.category == "environment"
        assert "quality_status_in" in metadata.parameters["properties"]
        assert "inventory" in metadata.description.lower()

    def test_get_openai_functions(self, registry) -> None:
        """Test getting OpenAI function schemas for registered tools."""
        functions = registry.get_openai_functions()

        assert len(functions) >= 21, f"Expected at least 21 environment tools, got {len(functions)}"

        for func in functions:
            assert "type" in func or "function" in func
            func_def = func.get("function", func)

            assert "name" in func_def
            assert "description" in func_def

    def test_filter_tools_by_category(self, registry) -> None:
        """Test filtering tools by category."""
        env_functions = registry.get_openai_functions(categories=["environment"])
        assert len(env_functions) == 21

        rag_functions = registry.get_openai_functions(categories=["rag"])
        assert (
            len(rag_functions) == 0
        ), "RAG tools should not be registered on import (loaded via MCP)"

    @pytest.mark.asyncio
    async def test_execute_tool_through_registry(self, registry) -> None:
        """Test executing an environment tool through registry."""
        tool = registry.get_tool("get_observed_inventory_snapshot")
        assert tool is not None
        assert tool.get_metadata().name == "get_observed_inventory_snapshot"
        assert tool.get_metadata().category == "environment"


class TestSkillToolsRegistration:
    """Test skill tools registration (dynamic loading via register_skill_tools)."""

    @pytest.fixture
    def registry(self):
        # We need a fresh empty registry to test skill injection
        return ToolRegistryFactory.create_react_agent_registry()

    @pytest.fixture(autouse=True)
    def cleanup_skill_tools(self) -> Generator[None, None, None]:
        yield
        import app.tools.registration

        app.tools.registration._global_skill_store = None

    @pytest.fixture
    def temp_skills_dir(self) -> Generator[Path, None, None]:
        """Create temporary skills directory with test skills."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir)

            skill_dir = skills_dir / "test-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                """---
name: test-skill
description: Test skill for registration testing
version: "1.0"
---

# Test Skill
Content here.
""",
                encoding="utf-8",
            )

            yield skills_dir

    def test_register_skill_tools(self, temp_skills_dir: Path, registry) -> None:
        """Test that register_skill_tools adds skill tools to registry."""
        tools_before = len(registry.tools)

        register_skill_tools(str(temp_skills_dir), registry=registry)

        tools_after = len(registry.tools)
        assert tools_after == tools_before + 2

        assert "load_skill" in registry.tools
        assert "read_skill_files" in registry.tools

    def test_skill_tools_are_cached(self, temp_skills_dir: Path, registry) -> None:
        """Test that skill tools are wrapped in CachedTool."""
        register_skill_tools(str(temp_skills_dir), registry=registry)

        load_tool = registry.get_tool("load_skill")
        read_batch_tool = registry.get_tool("read_skill_files")

        assert isinstance(load_tool, CachedTool)
        assert isinstance(read_batch_tool, CachedTool)

    def test_skill_tools_have_correct_category(self, temp_skills_dir: Path, registry) -> None:
        """Test that skill tools have category='skill'."""
        register_skill_tools(str(temp_skills_dir), registry=registry)

        load_tool = registry.get_tool("load_skill")
        read_batch_tool = registry.get_tool("read_skill_files")

        assert load_tool.get_metadata().category == "skill"
        assert read_batch_tool.get_metadata().category == "skill"

    def test_skill_tools_have_24h_ttl(self, temp_skills_dir: Path, registry) -> None:
        """Test that skill tools have 24-hour cache TTL (static knowledge)."""
        register_skill_tools(str(temp_skills_dir), registry=registry)

        load_tool = registry.get_tool("load_skill")
        read_batch_tool = registry.get_tool("read_skill_files")

        assert load_tool.get_metadata().cache_ttl == 86400  # 24 hours
        assert read_batch_tool.get_metadata().cache_ttl == 86400

    def test_skill_tools_dont_skip_cache(self, temp_skills_dir: Path, registry) -> None:
        """Test that skill tools use cache (not real-time data)."""
        register_skill_tools(str(temp_skills_dir), registry=registry)

        load_tool = registry.get_tool("load_skill")
        read_batch_tool = registry.get_tool("read_skill_files")

        assert load_tool.get_metadata().skip_cache is False
        assert read_batch_tool.get_metadata().skip_cache is False

    def test_skill_tools_include_in_openai_functions(self, temp_skills_dir: Path, registry) -> None:
        """Test that skill tools are included in OpenAI function schemas."""
        register_skill_tools(str(temp_skills_dir), registry=registry)

        functions = registry.get_openai_functions()
        function_names = {f["function"]["name"] for f in functions}

        assert "load_skill" in function_names
        assert "read_skill_files" in function_names

    def test_filter_skill_tools_by_category(self, temp_skills_dir: Path, registry) -> None:
        """Test filtering by skill category."""
        register_skill_tools(str(temp_skills_dir), registry=registry)

        skill_functions = registry.get_openai_functions(categories=["skill"])

        assert len(skill_functions) == 2
        function_names = {f["function"]["name"] for f in skill_functions}
        assert function_names == {"load_skill", "read_skill_files"}

    def test_register_skill_tools_with_empty_directory(self, registry) -> None:
        """Test registering skill tools with empty skills directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tools_before = len(registry.tools)

            register_skill_tools(tmpdir, registry=registry)

            tools_after = len(registry.tools)
            assert tools_after == tools_before + 2

            load_tool = registry.get_tool("load_skill")
            metadata = load_tool.get_metadata()
            param_desc = metadata.parameters["properties"]["skill_name"]["description"]
            assert "none" in param_desc.lower()

    @pytest.mark.asyncio
    async def test_execute_load_skill_tool(self, temp_skills_dir: Path, registry) -> None:
        """Test executing load_skill tool through registry."""
        register_skill_tools(str(temp_skills_dir), registry=registry)

        result = await registry.execute_tool("load_skill", {"skill_name": "test-skill"})

        assert result.success is True
        assert "skill_name" in result.data
        assert result.data["skill_name"] == "test-skill"

    @pytest.mark.asyncio
    async def test_execute_read_skill_files_tool_error(
        self, temp_skills_dir: Path, registry
    ) -> None:
        """Test executing read_skill_files tool with non-existent file."""
        register_skill_tools(str(temp_skills_dir), registry=registry)

        result = await registry.execute_tool(
            "read_skill_files", {"skill_name": "test-skill", "filenames": ["NONEXISTENT.md"]}
        )

        assert result.success is True
        assert "errors" in result.data
