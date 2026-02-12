# Contributing

## Setup

1. Install uv.
2. Install root-only tooling (without workspace packages):
   - `uv sync --no-install-workspace`
3. Optional install scopes:
   - All Python workspace packages/services (dev + extras):
     - `uv sync --all-packages --all-groups --all-extras`
   - Runtime-only Python dependencies (no dev groups):
     - `uv sync --all-packages --no-dev`
   - Selected workspace packages by project name:
     - `uv sync --package beliefcraft-common`
     - `uv sync --package beliefcraft-database --package beliefcraft-agent-service`
4. Install UI dependencies (Node.js):
   - `cd services/ui && npm install`

## Code quality (required)

We use:

- pre-commit runner to do checks on commit.
- Black: code formatter, rewrites Python code into a consistent style.
- Ruff: fast linter and auto-fixer.
- isort: sorts imports into a consistent order.
- mypy: checks your code's type hints without running it.

### Install git hooks

- `uv run pre-commit install`

### Run checks manually

- `uv run pre-commit run --all-files`

## CI

GitHub Actions runs the same checks. PRs must be green to merge.
