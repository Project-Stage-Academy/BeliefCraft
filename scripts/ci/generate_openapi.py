from pathlib import Path

import yaml
from environment_api.main import app


def generate_openapi():
    schema = app.openapi()

    out_dir = Path(__file__).parent.parent.parent / "docs" / "api"
    out_dir.mkdir(parents=True, exist_ok=True)

    out_file = out_dir / "environment-openapi.yaml"

    with Path.open(out_file, "w", encoding="utf-8") as f:
        yaml.dump(schema, f, sort_keys=False, allow_unicode=True)


if __name__ == "__main__":
    generate_openapi()
