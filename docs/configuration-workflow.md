# YAML Configuration Workflow

BeliefCraft services use externalized YAML config with validation through `ConfigLoader` in `packages/common/common/utils/config_loader.py`.

## Inputs and Outputs

- Input files:
  - `services/<service_name>/config/default.yaml`
  - optional: `services/<service_name>/config/dev.yaml`
  - optional: `services/<service_name>/config/prod.yaml`
  - optional local env file: `services/<service_name>/config/.env` (or repo `.env`)
- Output object:
  - A validated `pydantic.BaseModel` instance (attribute access, type-safe, required keys enforced).

## Path Precedence

Base config file resolution order:

1. `--config <path>` via `cli_config_path=...`
2. `<SERVICE_NAME>_CONFIG` environment variable (example: `ENVIRONMENT_API_CONFIG`)
3. `services/<service_name>/config/default.yaml`

Then optional `env` override is merged from `services/<service_name>/config/<env>.yaml` when the file exists.

## Environment Variable Placeholders

YAML values can include `${VAR_NAME}` placeholders.

Resolution order:

1. `services/<service_name>/config/.env` (if present)
2. repo root `.env` (if present)
3. `os.environ`

If a placeholder variable is missing, loader raises `MissingEnvironmentVariable` with the key path and the variable name.

## Usage Example

```python
import os
from pydantic import BaseModel, ConfigDict
from common.utils.config_loader import ConfigLoader


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    env: str


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    app: AppConfig


settings = ConfigLoader().load(
    service_name="environment-api",
    schema=Settings,
    env=os.getenv("ENV"),  # e.g. "dev", "prod"
    cli_config_path=None,  # pass from --config if present
)

print(settings.app.name)
```

## Error Handling

- `ConfigFileNotFound`: missing config directory/file.
- `ConfigParseError`: invalid YAML format or invalid `dotenv_mode`.
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
