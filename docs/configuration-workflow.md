# YAML Configuration Workflow

BeliefCraft services use externalized YAML config with validation through `ConfigLoader` in `packages/common/common/utils/config_loader.py`.

## Inputs and Outputs

- Input files:
  - `config/default.yaml`
  - optional: `config/dev.yaml`
  - optional: `config/prod.yaml`
  - optional local env file: `config/.env` (or service-root `.env`)
- Output object:
  - A validated `BaseSettings` instance (attribute access, type-safe, required keys enforced).

## Path Precedence

Base config file resolution order:

1. `--config <path>` via `cli_config_path=...`
2. `config_env_var` environment variable (example: `ENVIRONMENT_API_CONFIG`)
3. `config/default.yaml`

Then optional `env` override is merged from `config/<env>.yaml` when the file exists.

## Environment Variable Placeholders

YAML values can include `${VAR_NAME}` placeholders.

Resolution order:

1. `config/.env` (if present)
2. service-root `.env` (if present)
3. `os.environ`

If a placeholder variable is missing, loader raises `MissingEnvironmentVariable` with the key path and the variable name.

## Usage Example

```python
import os
from pathlib import Path
from pydantic import BaseModel
from common.utils.config_loader import ConfigLoader
from common.utils import BaseSettings


class AppConfig(BaseModel):
    name: str
    env: str


class Settings(BaseSettings):
    app: AppConfig


settings = ConfigLoader(
    service_root=Path(__file__).resolve().parents[2],
).load(
    schema=Settings,
    env=os.getenv("ENV"),  # e.g. "dev", "prod"
    cli_config_path=None,  # pass from --config if present
    config_env_var="ENVIRONMENT_API_CONFIG",
)

print(settings.app.name)
```

## Error Handling

- `ConfigFileNotFound`: missing config directory/file.
- `ConfigParseError`: invalid YAML format or invalid `dotenv_mode` (`config_dir_then_service_root` | `service_root_only` | `none`).
- `MissingEnvironmentVariable`: unresolved `${VAR_NAME}` placeholder.
- `ConfigValidationError`: schema validation failed.

## Tests

See `packages/common/tests/test_config_loader.py` for coverage of:

- default config load
- `dev` override merge
- path precedence
- `${VAR_NAME}` resolution order
- missing env variable errors
- validation failures
