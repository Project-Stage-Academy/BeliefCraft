import json

import pytest
from sync_mcp_config import (
    CodexTomlTransformer,
    ConfigSynchronizer,
    JsonTransformer,
    VsCodeTransformer,
)


@pytest.fixture
def mcp_data():
    return {
        "mcpServers": {
            "weaviate-docs": {"url": "https://weaviate-docs.mcp.kapa.ai", "type": "http"},
            "context7": {"url": "https://mcp.context7.com/mcp", "type": "http"},
        }
    }


def test_json_transformer_returns_valid_json(mcp_data):
    transformer = JsonTransformer()

    result = transformer.transform(mcp_data)

    parsed = json.loads(result)
    assert "mcpServers" in parsed
    assert parsed["mcpServers"] == mcp_data["mcpServers"]
    assert result.endswith("\n")


def test_vscode_transformer_uses_servers_key(mcp_data):
    transformer = VsCodeTransformer()

    result = transformer.transform(mcp_data)

    parsed = json.loads(result)
    assert "servers" in parsed
    assert "mcpServers" not in parsed
    assert parsed["servers"] == mcp_data["mcpServers"]


def test_codex_toml_transformer_returns_valid_toml(mcp_data):
    transformer = CodexTomlTransformer()

    result = transformer.transform(mcp_data)

    assert "[mcp_servers.weaviate-docs]" in result
    assert 'url = "https://weaviate-docs.mcp.kapa.ai"' in result
    assert "[mcp_servers.context7]" in result
    assert 'url = "https://mcp.context7.com/mcp"' in result


def test_synchronizer_updates_files(tmp_path, mcp_data):
    source_file = tmp_path / ".mcp.json"
    source_file.write_text(json.dumps(mcp_data))

    # Check VS Code specifically
    vscode_config = tmp_path / ".vscode/mcp.json"
    vscode_config.parent.mkdir(parents=True)
    vscode_config.write_text("{}")

    synchronizer = ConfigSynchronizer(tmp_path)

    changed = synchronizer.sync()

    assert changed is True
    assert json.loads(vscode_config.read_text())["servers"] == mcp_data["mcpServers"]


def test_synchronizer_skips_if_no_changes(tmp_path, mcp_data):
    source_file = tmp_path / ".mcp.json"
    source_file.write_text(json.dumps(mcp_data))
    synchronizer = ConfigSynchronizer(tmp_path)
    synchronizer.sync()  # First sync to align everything

    changed = synchronizer.sync()

    assert changed is False


def test_synchronizer_creates_missing_directories(tmp_path, mcp_data):
    source_file = tmp_path / ".mcp.json"
    source_file.write_text(json.dumps(mcp_data))
    synchronizer = ConfigSynchronizer(tmp_path)

    synchronizer.sync()

    assert (tmp_path / ".codex").is_dir()
    assert (tmp_path / ".cursor").is_dir()
    assert (tmp_path / ".gemini").is_dir()
    assert (tmp_path / ".vscode").is_dir()
