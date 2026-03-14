from pathlib import Path

from app.services.react_agent import ReActAgent

script_dir = Path(__file__).resolve().parent
repo_root = script_dir.parent.parent
docs_dir = repo_root / "docs" / "agent-service"


def generate_mermaid():
    docs_dir.mkdir(parents=True, exist_ok=True)

    agent = ReActAgent()
    mermaid_code = agent.graph.get_graph().draw_mermaid()

    output_path = docs_dir / "react_agent_graph.mmd"
    with open(output_path, "w") as f:
        f.write(mermaid_code)

    print(f"Saved diagram to: {output_path}")


if __name__ == "__main__":
    generate_mermaid()
