# RAG Service Configuration

The RAG Service uses a hierarchical configuration system based on YAML files and optional environment variable expansion.

## Configuration Files

The service looks for configuration in the `config/` directory relative to the service root:
1. `config/default.yaml`: Base configuration (required).
2. `config/{ENV}.yaml`: Environment-specific overrides (optional, e.g., `dev.yaml`, `prod.yaml`).

The environment is set via the `ENV` environment variable.

## Settings Reference

### `logging`
Controls the verbosity of various service components.
- `level` (default: `INFO`): Global log level for the service.

Below are log levels for noisy dependencies of fastmcp library
- `fakeredis_level` (default: `WARNING`): Log level for the `fakeredis` library.
- `docket_level` (default: `WARNING`): Log level for the `docket` library.
- `sse_level` (default: `WARNING`): Log level for the `sse_starlette` library.

### `repository`
Specifies which `AbstractVectorStoreRepository` implementation to use.
- Allowed values: `FakeDataRepository` (current).
- Default: `FakeDataRepository`.

## Example `default.yaml`

```yaml
logging:
  level: "INFO"
  fakeredis_level: "WARNING"
  docket_level: "WARNING"
  sse_level: "WARNING"

repository: "FakeDataRepository"
```
