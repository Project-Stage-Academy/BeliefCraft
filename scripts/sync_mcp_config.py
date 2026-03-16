import json
import sys
from abc import ABC, abstractmethod
from pathlib import Path


class ConfigTransformer(ABC):
    """Base class for configuration transformers."""

    @abstractmethod
    def transform(self, mcp_data: dict) -> str:
        """Converts raw MCP data into the target file format string."""
        pass


class JsonTransformer(ConfigTransformer):
    """Transformer for JSON-based configurations (Cursor, Gemini)."""

    def transform(self, mcp_data: dict) -> str:
        return json.dumps(mcp_data, indent=2) + "\n"


class VsCodeTransformer(ConfigTransformer):
    """Transformer for VS Code MCP configuration (uses 'servers' key)."""

    def transform(self, mcp_data: dict) -> str:
        data = {"servers": mcp_data.get("mcpServers", {})}
        return json.dumps(data, indent=2) + "\n"


class CodexTomlTransformer(ConfigTransformer):
    """Transformer for Codex TOML configuration."""

    def transform(self, mcp_data: dict) -> str:
        lines = []
        mcp_servers = mcp_data.get("mcpServers", {})
        for name, config in mcp_servers.items():
            lines.append(f"[mcp_servers.{name}]")
            if "url" in config:
                lines.append(f'url = "{config["url"]}"')
            lines.append("")
        return "\n".join(lines)


class ConfigSynchronizer:
    """Orchestrates the synchronization of MCP configurations across tools."""

    def __init__(self, root_path: Path):
        self.root_path = root_path
        self.source_path = root_path / ".mcp.json"
        self.targets = {
            ".cursor/mcp.json": JsonTransformer(),
            ".gemini/settings.json": JsonTransformer(),
            ".vscode/mcp.json": VsCodeTransformer(),
            ".codex/config.toml": CodexTomlTransformer(),
        }

    def sync(self) -> bool:
        """Synchronizes all target files with the source of truth.

        Returns:
            True if any changes were made, False otherwise.

        Raises:
            FileNotFoundError: If the source `.mcp.json` file does not exist.
        """
        if not self.source_path.exists():
            raise FileNotFoundError(f"Source of truth '{self.source_path}' not found.")

        with self.source_path.open() as f:
            mcp_data = json.load(f)

        changed = False
        for rel_path, transformer in self.targets.items():
            target_path = self.root_path / rel_path
            new_content = transformer.transform(mcp_data)

            existing_content = ""
            if target_path.exists():
                with target_path.open() as f:
                    existing_content = f.read()

            if existing_content != new_content:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with target_path.open("w") as f:
                    f.write(new_content)
                print(f"Updated {rel_path}")
                changed = True

        return changed


def main():
    """CLI entry point."""
    root = Path(__file__).parent.parent
    synchronizer = ConfigSynchronizer(root)
    try:
        if synchronizer.sync():
            print("Configurations synchronized successfully.")
        else:
            print("All configurations are already up to date.")
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
